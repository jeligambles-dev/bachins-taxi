"""/api/places/*: the Google Places (New) proxy behind the address search."""
import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import build
from content import default_content, merge
from server import places

KEY = "AIzaTEST-secret-key-1234567890"
SESSION = "abcDEF123_session"


@pytest.fixture
def papp(store, tmp_path):
    from server.app import create_app
    return create_app(store, tmp_path / "site", admin_password="correct-horse-battery",
                      secret_key="k", testing=True, google_maps_api_key=KEY)


@pytest.fixture
def pclient(papp):
    return papp.test_client()


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


@pytest.fixture
def upstream(monkeypatch):
    """Record requests to Google and answer with a queued payload or error."""
    calls, answers = [], []

    def fake(req, timeout=None):
        calls.append(req)
        a = answers.pop(0) if answers else {"suggestions": []}
        if isinstance(a, Exception):
            raise a
        return FakeResp(json.dumps(a).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return calls, answers


AC = {"suggestions": [
    {"placePrediction": {"placeId": "ChIJ_eircode_D15XW7K",
                         "text": {"text": "D15 XW7K, Macetown South, Dublin"},
                         "structuredFormat": {"mainText": {"text": "D15 XW7K"},
                                              "secondaryText": {"text": "Macetown South, Dublin"}}}},
    {"queryPrediction": {"text": {"text": "D15 cafes"}}},
]}


def test_autocomplete_trims_and_sends_the_right_request(pclient, upstream):
    calls, answers = upstream
    answers.append(AC)
    r = pclient.get(f"/api/places/autocomplete?q=D15 X&session={SESSION}")
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    assert r.get_json() == [{"id": "ChIJ_eircode_D15XW7K", "main": "D15 XW7K", "secondary": "Macetown South, Dublin"}]
    req = calls[0]
    body = json.loads(req.data)
    assert req.full_url == places.AUTOCOMPLETE_URL and req.get_method() == "POST"
    assert req.get_header("X-goog-api-key") == KEY
    assert body["input"] == "D15 X" and body["sessionToken"] == SESSION
    assert body["includedRegionCodes"] == ["ie", "gb"] and body["languageCode"] == "en"
    assert body["locationRestriction"]["rectangle"] == places.IRELAND
    assert KEY not in r.get_data(as_text=True)


@pytest.mark.parametrize("qs", ["q=a&session=" + SESSION, "q=" + "x" * 101 + "&session=" + SESSION,
                                "q=Lucan&session=short", "q=Lucan&session=bad%20token!!", "q=Lucan"])
def test_autocomplete_validation(pclient, upstream, qs):
    assert pclient.get("/api/places/autocomplete?" + qs).status_code == 400
    assert upstream[0] == []


@pytest.mark.parametrize("qs", ["id=short&session=" + SESSION, "id=ChIJ/../etc/passwd&session=" + SESSION,
                                "id=ChIJabcdefghij&session=x"])
def test_details_validation(pclient, upstream, qs):
    assert pclient.get("/api/places/details?" + qs).status_code == 400


def test_not_configured_without_key(client, upstream):
    for url in (f"/api/places/autocomplete?q=Lucan&session={SESSION}",
                f"/api/places/details?id=ChIJabcdefghij&session={SESSION}"):
        r = client.get(url)
        assert r.status_code == 503 and r.get_json() == {"error": "not_configured"}
    assert upstream[0] == []


def test_foreign_origin_rejected(pclient, upstream):
    r = pclient.get(f"/api/places/autocomplete?q=Lucan&session={SESSION}", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    ok = pclient.get(f"/api/places/autocomplete?q=Lucan&session={SESSION}", headers={"Origin": "http://localhost"})
    assert ok.status_code == 200


def test_rate_limit(pclient, upstream):
    for i in range(60):
        assert pclient.get(f"/api/places/autocomplete?q=query{i}&session={SESSION}").status_code == 200
    assert pclient.get(f"/api/places/autocomplete?q=one-more&session={SESSION}").status_code == 429
    for i in range(30):
        upstream[1].append({"id": "x"})
        assert pclient.get(f"/api/places/details?id=ChIJplace{i:06d}&session={SESSION}").status_code == 200
    assert pclient.get(f"/api/places/details?id=ChIJplace999999&session={SESSION}").status_code == 429


def test_no_caching_of_google_results(pclient, upstream):
    # Google Maps Platform terms: Places content is not cached or stored, so
    # two identical queries both go to Google.
    calls, answers = upstream
    answers.extend([AC, AC])
    a = pclient.get(f"/api/places/autocomplete?q=D15 X&session={SESSION}").get_json()
    b = pclient.get(f"/api/places/autocomplete?q=D15 X&session={SESSION}").get_json()
    assert a == b and len(calls) == 2
    assert "places_cache" not in pclient.application.extensions


def test_upstream_error_is_502_without_leaking(pclient, upstream):
    calls, answers = upstream
    leak = b'{"error": {"message": "API key AIzaTEST-secret-key-1234567890 not valid for request"}}'
    answers.append(urllib.error.HTTPError(places.AUTOCOMPLETE_URL, 403, "Forbidden", {}, io.BytesIO(leak)))
    r = pclient.get(f"/api/places/autocomplete?q=Lucan&session={SESSION}")
    assert r.status_code == 502 and r.get_json() == {"error": "unavailable"}
    assert b"not valid" not in r.data and KEY.encode() not in r.data
    answers.append(TimeoutError("timed out"))
    r = pclient.get(f"/api/places/details?id=ChIJabcdefghij&session={SESSION}")
    assert r.status_code == 502 and r.get_json() == {"error": "unavailable"}


def test_details_request_and_field_mask(pclient, upstream):
    calls, answers = upstream
    answers.append(EIRCODE_PLACE)
    r = pclient.get(f"/api/places/details?id=ChIJ_eircode_D15XW7K&session={SESSION}")
    assert r.status_code == 200 and r.get_json()["postcode"] == "D15 XW7K"
    req = calls[0]
    assert req.full_url.startswith(places.DETAILS_URL + "ChIJ_eircode_D15XW7K?sessionToken=" + SESSION)
    assert req.get_header("X-goog-fieldmask") == places.DETAILS_FIELDS
    assert req.get_header("X-goog-api-key") == KEY


# ── details normaliser ───────────────────────────────────────────────────────

def comp(text, *types):
    return {"longText": text, "shortText": text, "types": list(types)}


EIRCODE_PLACE = {
    "id": "ChIJ_eircode_D15XW7K", "displayName": {"text": "D15 XW7K"},
    "formattedAddress": "Macetown South, Dublin 15, Co. Dublin, D15 XW7K, Ireland",
    "location": {"latitude": 53.408, "longitude": -6.402}, "types": ["postal_code"],
    "addressComponents": [comp("d15 xw7k", "postal_code"), comp("Macetown South", "sublocality_level_1", "sublocality"),
                          comp("Dublin 15", "locality", "political"), comp("County Dublin", "administrative_area_level_1")],
}
AIRPORT_PLACE = {
    "id": "ChIJairport", "displayName": {"text": "Dublin Airport"},
    "formattedAddress": "Collinstown, Dublin, Ireland", "location": {"latitude": 53.4265, "longitude": -6.2499},
    "types": ["airport", "point_of_interest", "establishment"],
    "addressComponents": [comp("Collinstown", "locality"), comp("County Dublin", "administrative_area_level_1")],
}
SANTRY_PARK = {
    "id": "ChIJsantry", "displayName": {"text": "Dublin Airport Business Park"},
    "formattedAddress": "Santry, Dublin 9, Ireland", "location": {"latitude": 53.4036, "longitude": -6.2420},
    "types": ["point_of_interest", "establishment"],
    "addressComponents": [comp("Santry", "sublocality_level_1"), comp("Dublin 9", "locality"),
                          comp("County Dublin", "administrative_area_level_1")],
}


def test_normalise_eircode_place():
    d = places.normalise_details(EIRCODE_PLACE)
    assert d["postcode"] == "D15 XW7K" and d["sublocality"] == "Macetown South" and d["locality"] == "Dublin 15"
    assert d["county"] == "County Dublin" and d["is_airport"] is False
    assert d["label"] == "Macetown South, Dublin 15, Co. Dublin, D15 XW7K" and d["lat"] == 53.408


def test_normalise_dublin_airport():
    d = places.normalise_details(AIRPORT_PLACE)
    assert d["is_airport"] is True and d["label"].startswith("Dublin Airport, Collinstown")


def test_normalise_santry_business_park_is_not_the_airport():
    d = places.normalise_details(SANTRY_PARK)
    assert d["is_airport"] is False and d["sublocality"] == "Santry"


def test_terminal_coordinates_count_as_airport():
    near_t2 = dict(SANTRY_PARK, location={"latitude": 53.4262, "longitude": -6.2395}, types=["parking"])
    assert places.normalise_details(near_t2)["is_airport"] is True


def test_key_never_in_built_site(tmp_path, papp):
    build.build_site(merge(default_content(), {}), tmp_path / "out")
    for p in (tmp_path / "out").rglob("*"):
        if p.is_file() and p.suffix in (".html", ".js", ".json", ".xml", ".txt", ".css"):
            assert KEY not in p.read_text(), p
    root = Path(build.ROOT_DIR)
    for p in list((root / "js").glob("*.js")) + list((root / "build").glob("**/*.html")):
        assert KEY not in p.read_text()
