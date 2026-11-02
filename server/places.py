"""Address search for the public booking forms, proxied to Google Places (New).

The browser never sees the API key: it calls our /api/places/* endpoints,
which validate input, rate-limit per client IP, cache autocomplete results
and return a trimmed response. Upstream errors become a plain 502 so Google's
error bodies (which can echo request details) never reach the client.
"""
import json
import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict, defaultdict, deque
from urllib.parse import urlparse

from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("places", __name__)

AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"
DETAILS_URL = "https://places.googleapis.com/v1/places/"
DETAILS_FIELDS = "id,displayName,formattedAddress,location,addressComponents,types"
TIMEOUT = 4
IRELAND = {"low": {"latitude": 51.3, "longitude": -10.8},
           "high": {"latitude": 55.5, "longitude": -5.3}}
TERMINALS = ((53.4273, -6.2441), (53.4264, -6.2390))   # Dublin Airport T1, T2
AIRPORT_RADIUS_KM = 1.0

SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
PLACE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,300}$")


class Upstream(Exception):
    """Google could not be reached or answered with an error."""


# ── Rate limit and cache ─────────────────────────────────────────────────────

class RateLimiter:
    """Sliding one-minute window per (bucket, client). In-memory and per
    process, like the admin login limiter."""

    def __init__(self, limits, clock=time.monotonic):
        self.limits = dict(limits)          # bucket -> max requests per minute
        self._clock = clock
        self._lock = threading.Lock()
        self._hits = defaultdict(deque)

    def allow(self, bucket, key):
        now = self._clock()
        with self._lock:
            q = self._hits[(bucket, key)]
            while q and now - q[0] >= 60:
                q.popleft()
            if len(q) >= self.limits[bucket]:
                return False
            q.append(now)
            return True

    def reset(self):
        with self._lock:
            self._hits.clear()


class TTLCache:
    """Small LRU with a time-to-live, for autocomplete results."""

    def __init__(self, size=500, ttl=600, clock=time.monotonic):
        self.size, self.ttl, self._clock = size, ttl, clock
        self._lock = threading.Lock()
        self._data = OrderedDict()

    def get(self, key):
        with self._lock:
            hit = self._data.get(key)
            if not hit:
                return None
            stamp, value = hit
            if self._clock() - stamp > self.ttl:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def put(self, key, value):
        with self._lock:
            self._data[key] = (self._clock(), value)
            self._data.move_to_end(key)
            while len(self._data) > self.size:
                self._data.popitem(last=False)


# ── Google calls ─────────────────────────────────────────────────────────────

def _call(req):
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise Upstream(type(e).__name__) from None


def google_autocomplete(key, text, session):
    body = json.dumps({
        "input": text, "sessionToken": session, "languageCode": "en",
        "includedRegionCodes": ["ie", "gb"],          # Northern Ireland is GB
        "locationRestriction": {"rectangle": IRELAND},
    }).encode()
    req = urllib.request.Request(AUTOCOMPLETE_URL, data=body, method="POST", headers={
        "Content-Type": "application/json", "X-Goog-Api-Key": key})
    return trim_suggestions(_call(req))


def google_details(key, place_id, session):
    url = DETAILS_URL + urllib.parse.quote(place_id, safe="") + "?" + urllib.parse.urlencode({"sessionToken": session})
    req = urllib.request.Request(url, method="GET", headers={
        "X-Goog-Api-Key": key, "X-Goog-FieldMask": DETAILS_FIELDS})
    return normalise_details(_call(req))


# ── Normalisers (pure) ───────────────────────────────────────────────────────

def trim_suggestions(data):
    """Google autocomplete -> [{id, main, secondary}], at most 6 places."""
    out = []
    for s in (data or {}).get("suggestions") or []:
        p = s.get("placePrediction") if isinstance(s, dict) else None
        if not isinstance(p, dict) or not p.get("placeId"):
            continue
        fmt = p.get("structuredFormat") or {}
        main = ((fmt.get("mainText") or {}).get("text") or (p.get("text") or {}).get("text") or "").strip()
        secondary = ((fmt.get("secondaryText") or {}).get("text") or "").strip()
        if main:
            out.append({"id": p["placeId"], "main": main, "secondary": secondary})
        if len(out) == 6:
            break
    return out


def _km(a, b):
    r = math.pi / 180
    dlat, dlon = (b[0] - a[0]) * r, (b[1] - a[1]) * r
    h = math.sin(dlat / 2) ** 2 + math.cos(a[0] * r) * math.cos(b[0] * r) * math.sin(dlon / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def normalise_details(place):
    """Google place details -> {label, lat, lon, postcode, locality,
    sublocality, county, types, is_airport}."""
    place = place or {}
    comps = place.get("addressComponents") or []

    def comp(*kinds):
        for kind in kinds:
            for c in comps:
                if kind in (c.get("types") or []):
                    return (c.get("longText") or c.get("shortText") or "").strip()
        return ""

    loc = place.get("location") or {}
    lat, lon = loc.get("latitude"), loc.get("longitude")
    types = [t for t in (place.get("types") or []) if isinstance(t, str)]
    postcode = re.sub(r"\s+", " ", comp("postal_code").upper()).strip()
    name = ((place.get("displayName") or {}).get("text") or "").strip()
    address = (place.get("formattedAddress") or "").strip()
    address = re.sub(r",\s*(Ireland|UK|United Kingdom)$", "", address)
    squash = lambda t: re.sub(r"\s+", "", t).lower()  # noqa: E731
    label = address if (not name or squash(name) in squash(address)) else f"{name}, {address}"
    if postcode and postcode.replace(" ", "") not in label.upper().replace(" ", ""):
        label = f"{label}, {postcode}" if label else postcode
    near = (isinstance(lat, (int, float)) and isinstance(lon, (int, float))
            and any(_km((lat, lon), t) <= AIRPORT_RADIUS_KM for t in TERMINALS))
    return {
        "label": label, "lat": lat, "lon": lon, "postcode": postcode,
        "locality": comp("locality", "postal_town"),
        "sublocality": comp("sublocality_level_1", "sublocality", "neighborhood"),
        "county": comp("administrative_area_level_1", "administrative_area_level_2"),
        "types": types, "is_airport": "airport" in types or near,
    }


# ── Endpoints ────────────────────────────────────────────────────────────────

def _json(payload, status=200):
    resp = jsonify(payload)
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _guard(bucket):
    """Common checks; returns (key, error response or None)."""
    origin = request.headers.get("Origin")
    if origin and urlparse(origin).netloc != request.host:
        return None, _json({"error": "forbidden"}, 403)
    key = current_app.config.get("GOOGLE_MAPS_API_KEY") or ""
    if not key:
        return None, _json({"error": "not_configured"}, 503)
    if not current_app.extensions["places_limiter"].allow(bucket, request.remote_addr or "?"):
        return None, _json({"error": "rate_limited"}, 429)
    return key, None


@bp.get("/api/places/autocomplete")
def autocomplete():
    q = (request.args.get("q") or "").strip()
    session = request.args.get("session") or ""
    if not (2 <= len(q) <= 100) or not SESSION_RE.match(session):
        return _json({"error": "bad_request"}, 400)
    key, err = _guard("autocomplete")
    if err:
        return err
    cache = current_app.extensions["places_cache"]
    hit = cache.get(q.lower())
    if hit is not None:
        return _json(hit)
    try:
        result = google_autocomplete(key, q, session)
    except Upstream:
        return _json({"error": "unavailable"}, 502)
    cache.put(q.lower(), result)
    return _json(result)


@bp.get("/api/places/details")
def details():
    place_id = request.args.get("id") or ""
    session = request.args.get("session") or ""
    if not PLACE_ID_RE.match(place_id) or not SESSION_RE.match(session):
        return _json({"error": "bad_request"}, 400)
    key, err = _guard("details")
    if err:
        return err
    try:
        return _json(google_details(key, place_id, session))
    except Upstream:
        return _json({"error": "unavailable"}, 502)


def init_app(app, api_key=None):
    app.config["GOOGLE_MAPS_API_KEY"] = api_key or ""
    app.extensions["places_limiter"] = RateLimiter({"autocomplete": 60, "details": 30})
    app.extensions["places_cache"] = TTLCache(size=500, ttl=600)
    app.register_blueprint(bp)
