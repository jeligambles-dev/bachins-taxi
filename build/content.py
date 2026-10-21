"""Content model: defaults from data.py, owner overrides, validation."""
import copy
import re

import data

SECTIONS = ("settings", "texts", "tours", "multi_day", "airport_fares",
            "long_transfers", "photo_slots", "redirects", "flags")
KINDS = {"day": "Day tour", "pub": "Rural pub tour", "golf": "Golf trip"}

_DICT_SECTIONS = ("settings", "texts", "photo_slots", "flags")
_LIST_SECTIONS = ("multi_day", "airport_fares", "long_transfers")
_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class ValidationError(Exception):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def normalize_tour(t):
    out = {"kind": "day", "published": True, "fav": False, "price": None,
           "photo": None, "area": "", "drive": "", "highlights": [],
           "intro": "", "desc": "", "duration": "", "region": ""}
    out.update(copy.deepcopy(t))
    return out


def default_content():
    tours = [normalize_tour(t) for t in data.TOURS + data.EXTRA_TOURS]
    return {
        "settings": {
            "phone": data.PHONE,
            "phone_display": data.PHONE_DISPLAY,
            "email": data.EMAIL,
            "whatsapp_number": data.WHATSAPP.rsplit("/", 1)[-1],
            "site_url": data.SITE_URL,
            "multi_day_rate": data.MULTI_DAY_RATE,
            "extra_hour_rate": data.EXTRA_HOUR_RATE,
            "max_passengers": data.MAX_PASSENGERS,
        },
        "texts": {},
        "tours": tours,
        "multi_day": copy.deepcopy(data.MULTI_DAY),
        "airport_fares": [{"area": a, "distance": d, "to": to, "from": fr}
                          for a, d, to, fr in data.AIRPORT_FARES],
        "long_transfers": [{"area": a, "price": p}
                           for a, p in data.LONG_TRANSFERS],
        "photo_slots": {"hero": None, "taxi": None, "logo": None},
        "redirects": {},
        "flags": {},
    }


def merge(defaults, stored):
    stored = stored or {}
    out = copy.deepcopy(defaults)
    for k in _DICT_SECTIONS:
        if isinstance(stored.get(k), dict):
            out.setdefault(k, {}).update(copy.deepcopy(stored[k]))
    for k in _LIST_SECTIONS + ("tours",):
        if k in stored and stored[k] is not None:
            out[k] = copy.deepcopy(stored[k])
    if isinstance(stored.get("redirects"), dict):
        out["redirects"] = copy.deepcopy(stored["redirects"])
    out["tours"] = [normalize_tour(t) for t in out["tours"]]
    return out


def price_label(t):
    p = t.get("price")
    if p is None:
        return "Price on request"
    return f"€{p:,}"


def price_unit(t):
    return "per trip" if t.get("kind") == "golf" else "per vehicle"


def validate_tour(t, others):
    errors = []
    slug = t.get("slug")
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        errors.append("The web address (slug) must use only lowercase letters, "
                      "numbers and single hyphens, e.g. my-new-tour.")
    elif any(o.get("slug") == slug for o in others):
        errors.append(f"Another tour already uses the web address \"{slug}\".")
    name = t.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("The tour name cannot be empty.")
    if t.get("kind") not in KINDS:
        errors.append("Choose a valid tour type.")
    p = t.get("price")
    if p is not None and (isinstance(p, bool) or not isinstance(p, int)
                          or not 0 <= p <= 100000):
        errors.append("The price must be a whole number of euros from 0 to "
                      "100,000, or left blank.")
    return errors


def resolve_redirect(slug, redirects):
    """Follow `redirects` from `slug` to its current target (loop-safe)."""
    seen = set()
    while slug in redirects and slug not in seen:
        seen.add(slug)
        slug = redirects[slug]
    return slug


def rename_slug(content_sections, old, new):
    """Rename a tour's slug. Returns {"tours": [...], "redirects": {...}}.

    The old address redirects to the new one; earlier redirects to `old` are
    repointed; a redirect from `new` is dropped (the slug is live again).
    """
    tours = copy.deepcopy(content_sections["tours"])
    redirects = dict(content_sections.get("redirects") or {})
    tour = next((t for t in tours if t.get("slug") == old), None)
    if tour is None:
        raise ValidationError([f"There is no tour with the web address \"{old}\"."])
    if new == old:
        return {"tours": tours, "redirects": redirects}
    errors = validate_tour(dict(tour, slug=new), [t for t in tours if t is not tour])
    if errors:
        raise ValidationError(errors)
    tour["slug"] = new
    redirects.pop(new, None)
    redirects = {k: (new if v == old else v) for k, v in redirects.items()}
    redirects[old] = new
    return {"tours": tours,
            "redirects": {k: v for k, v in redirects.items() if k != v}}


_TOUR_LINK_RE = re.compile(r"tours/([a-z0-9-]+)\.html")


def blog_links_to(slug, redirects):
    """Titles of blog posts that link to the tour `slug`, directly or through
    a redirect source that resolves to it."""
    from posts import POSTS
    return [p["title"] for p in POSTS
            if any(resolve_redirect(m, redirects) == slug
                   for m in _TOUR_LINK_RE.findall(p["body"]))]
