#!/usr/bin/env python3
"""Generate the BCH Group site from build/data.py and build/posts.py.

Usage:  python3 build/build.py [--out DIR]     (default DIR: dist/)

build_site(content, out_dir) renders the whole site into out_dir:
- index.html from build/templates/index.html (marked regions filled in)
- fleet.html, business.html, partners.html, help.html,
  tours.html, tours/*.html, multi-day-tours.html, price-calculator.html,
  destinations.html, blog.html and blog/*.html, sitemap.xml, robots.txt
- copies css/, js/ and images/
- checks every local link and asset exists (raises BuildError otherwise)
"""
import hashlib
import html
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from data import AREAS      # noqa: E402
from content import (KINDS, default_content, merge, price_label,  # noqa: E402
                     price_unit, resolve_redirect, _SLUG_RE)
from posts import POSTS     # noqa: E402
import texts                # noqa: E402
from texts import T, T_lines  # noqa: E402

_BRACE_RE = re.compile(r"\{(?=\{)")


def E(value, quote=True):
    """html.escape plus: owner text can never contain a literal "{{", so it
    can neither break the leftover-token check nor forge a contact token."""
    return _BRACE_RE.sub("&#123;", html.escape(value, quote=quote))


def _ld_dumps(obj, **kw):
    """JSON-LD / inline JSON for owner data, with "{{" neutralised."""
    out = json.dumps(obj, ensure_ascii=False, **kw).replace("<", "\\u003c")
    return _BRACE_RE.sub(lambda m: "\\u007b", out)


_PHOTO_RE = re.compile(r"^uploads/[a-z0-9]+\.(jpg|png)$")
PARTIALS = Path(__file__).resolve().parent / "partials"
_MODAL_RAW = (PARTIALS / "modal.html").read_text().strip()
_FAB_RAW = (PARTIALS / "fab.html").read_text().strip()
MODAL = FAB = ""    # the partials with contact tokens filled, set by _configure()

TEMPLATE_INDEX = Path(__file__).resolve().parent / "templates" / "index.html"

# Module-level context, (re)bound by build_site() via _configure(). Every
# builder below reads these names.
PHONE = PHONE_DISPLAY = EMAIL = WHATSAPP = SITE_URL = ""
MULTI_DAY_RATE = EXTRA_HOUR_RATE = MAX_PASSENGERS = 0
CONFIG_JS = CONFIG_VER = ""   # js/config.js text and its cache-busting hash
TOURS = []          # every tour, published or hidden
TOUR_BY_SLUG = {}
MULTI_DAY = []
AIRPORT_FARES = []
LONG_TRANSFERS = []
REDIRECTS = {}      # old tour slug -> new slug
SLOT_PHOTO = {}     # "hero" / "taxi" / "logo" -> site-relative path, if set
TOUR_PHOTO = {}     # tour slug -> site-relative path, if set
FLEET = []          # every vehicle, published or hidden
VEHICLE_PHOTO = {}  # vehicle slug -> site-relative path, if an admin photo is set
VAN_SLUG = "van"    # the fixed tour and airport prices are for this vehicle


class BuildError(Exception):
    def __init__(self, broken, message="Broken links"):
        self.broken = list(broken)
        super().__init__(message + ": " + "; ".join(self.broken))


KIND_ORDER = ("day", "pub", "golf")
# Page that lists each kind, with its breadcrumb name and nav key.
KIND_PAGE = {
    "day": ("tours.html", "Tours", "tours"),
    "pub": ("pub-tours.html", "Pub tours", "pub"),
    "golf": ("golf-trips.html", "Golf trips", "golf"),
}
KIND_SUFFIX = {"day": "Private Tour", "pub": "Rural Pub Tour", "golf": "Golf Trip"}
KIND_NOUN = {"day": "day tour", "pub": "rural pub tour", "golf": "golf trip"}


def published(kind=None):
    """Published tours (optionally of one kind), day first, then pub, then golf."""
    kinds = KIND_ORDER if kind is None else (kind,)
    return [t for k in kinds for t in TOURS if t["kind"] == k and t["published"]]


def _configure(content):
    global PHONE, PHONE_DISPLAY, EMAIL, WHATSAPP, SITE_URL
    global MULTI_DAY_RATE, EXTRA_HOUR_RATE, MAX_PASSENGERS
    global TOURS, TOUR_BY_SLUG, MULTI_DAY, AIRPORT_FARES, LONG_TRANSFERS
    global MODAL, FAB, CONFIG_JS, CONFIG_VER, REDIRECTS, SLOT_PHOTO, TOUR_PHOTO
    global FLEET, VEHICLE_PHOTO
    st = content["settings"]
    texts.configure(content.get("texts"), st["max_passengers"])
    PHONE = st["phone"]
    PHONE_DISPLAY = st["phone_display"]
    EMAIL = st["email"]
    WHATSAPP = "https://wa.me/" + st["whatsapp_number"]
    SITE_URL = st["site_url"]
    MULTI_DAY_RATE = st["multi_day_rate"]
    EXTRA_HOUR_RATE = st["extra_hour_rate"]
    MAX_PASSENGERS = st["max_passengers"]
    TOURS = list(content["tours"])
    TOUR_BY_SLUG = {t["slug"]: t for t in TOURS}
    MULTI_DAY = content["multi_day"]
    AIRPORT_FARES = [(f["area"], f["distance"], f["to"], f["from"]) for f in content["airport_fares"]]
    LONG_TRANSFERS = [(f["area"], f["price"]) for f in content["long_transfers"]]
    REDIRECTS = dict(content.get("redirects") or {})
    paths = {pid: p for pid, p in (content.get("_photos") or {}).items()
             if isinstance(p, str) and _PHOTO_RE.match(p)}
    SLOT_PHOTO = {slot: paths[pid] for slot, pid in (content.get("photo_slots") or {}).items()
                  if isinstance(pid, str) and pid in paths}
    TOUR_PHOTO = {t["slug"]: paths[t["photo"]] for t in TOURS if isinstance(t.get("photo"), str) and t["photo"] in paths}
    FLEET = list(content.get("fleet") or [])
    VEHICLE_PHOTO = {v["slug"]: paths[v["photo"]] for v in FLEET
                     if isinstance(v.get("photo"), str) and v["photo"] in paths}
    MODAL = fill_tokens(texts.dyn(_MODAL_RAW))
    FAB = fill_tokens(_FAB_RAW)
    CONFIG_JS = ("window.BCH = " + _json_inline({
        "email": EMAIL, "waNumber": st["whatsapp_number"],
        "phoneDisplay": PHONE_DISPLAY, "maxPax": MAX_PASSENGERS}) + ";\n")
    CONFIG_VER = hashlib.sha256(CONFIG_JS.encode()).hexdigest()[:8]


# ── Contact tokens ───────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"\{\{[A-Z_]+\}\}")
_LD_RE = re.compile(r'(<script type="application/ld\+json">)(.*?)(</script>)', re.S)


def _json_inline(obj):
    """JSON that is safe inside a <script> element."""
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")


def _token_values():
    return {"{{PHONE}}": PHONE, "{{PHONE_DISPLAY}}": PHONE_DISPLAY,
            "{{EMAIL}}": EMAIL, "{{WA_NUMBER}}": WHATSAPP.rsplit("/", 1)[-1]}


def fill_tokens(s):
    """Fill {{PHONE}}, {{PHONE_DISPLAY}}, {{EMAIL}}, {{WA_NUMBER}}.

    HTML-escaped everywhere except inside JSON-LD blocks, where the values are
    JSON-escaped.
    """
    values = _token_values()

    def fill(text, conv):
        for tok, val in values.items():
            text = text.replace(tok, conv(val))
        return text

    def json_conv(v):
        return _json_inline(v)[1:-1]

    out, pos = [], 0
    for m in _LD_RE.finditer(s):
        out.append(fill(s[pos:m.start()], html.escape))
        out.append(m.group(1) + fill(m.group(2), json_conv) + m.group(3))
        pos = m.end()
    out.append(fill(s[pos:], html.escape))
    return "".join(out)


def photo_url(slot, root, default, absolute=True):
    """URL for a photo slot (or the default image), as seen from a page at `root`.
    Absolute when SITE_URL is set and `absolute`, else relative to `root`."""
    path = SLOT_PHOTO.get(slot, default)
    if absolute and SITE_URL:
        return E(SITE_URL.rstrip("/") + "/" + path)
    return E(root + path)


def tour_photo(t, root, cls="tour-photo", lazy=True):
    path = TOUR_PHOTO.get(t["slug"])
    if not path:
        return ""
    return (f'<img class="{cls}" src="{E(root + path)}" alt="{E(t["name"])}"'
            + (' loading="lazy"' if lazy else "") + ">")


def config_script(root):
    return f'<script src="{root}js/config.js?v={CONFIG_VER}"></script>'


def asset(rel):
    """css/js path with a content hash, so a deploy busts the browser cache."""
    return f"{rel}?v={hashlib.sha256((ROOT_DIR / rel).read_bytes()).hexdigest()[:8]}"


def eur(n):
    return f"€{n:,}"


def multi_price(m):
    return m["days"] * MULTI_DAY_RATE


def idx(root, anchor, is_index):
    """Link to a section of the home page."""
    return f"#{anchor}" if is_index else f"{root}index.html#{anchor}"


# ── Shared chrome ────────────────────────────────────────────────────────────

def brand(root):
    """The BCH logo (transparent PNG, 2x for sharp screens)."""
    return f'<img class="brand-logo" src="{root}images/logo.png" alt="BCH Group" width="498" height="192">'


NAV_TOURS = (("Day tours", "tours.html", "tours"), ("Pub tours", "pub-tours.html", "pub"),
             ("Golf", "golf-trips.html", "golf"), ("Multi-day", "multi-day-tours.html", "multi"),
             ("Price calculator", "price-calculator.html", "prices"))


def nav(root, is_index=False, active=""):
    current = ' aria-current="page"'
    home = "#" if is_index else f"{root}index.html"

    def li(label, href, key):
        return f'      <li><a href="{href}"{current if key == active else ""}>{label}</a></li>'

    sub = "\n".join(f'          <li><a href="{root}{h}"{current if k == active else ""}>{l}</a></li>'
                    for l, h, k in NAV_TOURS)
    cls = "has-sub in-section" if active in {k for _, _, k in NAV_TOURS} else "has-sub"
    tours_li = (f'      <li class="{cls}"><a href="{root}tours.html">Tours</a>\n'
                f'        <ul class="nav-sub">\n{sub}\n        </ul>\n      </li>')
    lis = "\n".join([
        li("Personal", home, "personal"),
        li("Business", f"{root}business.html", "business"),
        li("Partners", f"{root}partners.html", "partners"),
        li("Fleet", f"{root}fleet.html", "fleet"),
        tours_li,
        li("Help", f"{root}help.html", "help"),
    ])
    return f"""  <nav class="site-nav">
    <a href="{home}" class="brand" aria-label="BCH Group home">
      {brand(root)}
    </a>
    <ul class="nav-links" id="nav-links">
{lis}
      <li class="nav-book"><a href="{idx(root, 'booking', is_index)}" class="btn btn-primary">Book</a></li>
    </ul>
    <a class="nav-call" href="tel:{E(PHONE)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.8 19.8 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/></svg><span class="nav-call-short">Call</span><span class="nav-call-num">{E(PHONE_DISPLAY)}</span></a>
    <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="nav-links">Menu</button>
  </nav>"""


def footer(root, is_index=False):
    home = "#" if is_index else root + "index.html"
    return f"""  <footer class="site-footer">
    <div class="footer-top">
      <a href="{home}" class="brand" aria-label="BCH Group home">
        {brand(root)}
      </a>
      <p>{T("footer.about")}</p>
    </div>
    <div class="footer-grid">
      <div>
        <h4>Personal</h4>
        <ul>
          <li><a href="{root}index.html?service=Airport%20transfer#booking">Airport transfers</a></li>
          <li><a href="{root}tours.html">Day tours</a></li>
          <li><a href="{root}pub-tours.html">Pub tours</a></li>
          <li><a href="{root}golf-trips.html">Golf trips</a></li>
          <li><a href="{root}multi-day-tours.html">Multi-day tours</a></li>
          <li><a href="{root}price-calculator.html">Price calculator</a></li>
        </ul>
      </div>
      <div>
        <h4>Business</h4>
        <ul>
          <li><a href="{root}business.html">Business travel</a></li>
          <li><a href="{root}partners.html">Partners</a></li>
          <li><a href="{root}fleet.html">Fleet</a></li>
        </ul>
      </div>
      <div>
        <h4>Company</h4>
        <ul>
          <li><a href="{root}help.html">Help centre</a></li>
          <li><a href="{root}destinations.html">Destinations</a></li>
          <li><a href="{root}blog.html">Travel guides</a></li>
        </ul>
      </div>
      <div>
        <h4>Contact</h4>
        <ul class="footer-contact">
          <li><a href="tel:{E(PHONE)}">{E(PHONE_DISPLAY)}</a></li>
          <li><a href="{E(WHATSAPP)}" target="_blank" rel="noopener">WhatsApp</a></li>
          <li><a href="mailto:{E(EMAIL)}">{E(EMAIL)}</a></li>
        </ul>
      </div>
    </div>
    <div class="footer-bottom">
      <p>&copy; 2026 BCH Group</p>
      <p>{T("footer.tagline")}</p>
    </div>
  </footer>"""


def fix_root(fragment, root):
    """Partials are written for the site root; point their links at `root`."""
    return fragment.replace('href="index.html', f'href="{root}index.html')


def page(*, root, title, description, body, active="", path="", jsonld=None, extra_js="", noindex=False):
    canonical = ""
    if SITE_URL:
        canonical = f'\n  <link rel="canonical" href="{SITE_URL.rstrip("/")}/{path}">'
    ld = ""
    for block in (jsonld or []):
        ld += '\n  <script type="application/ld+json">\n' + _ld_dumps(block, indent=2) + "\n  </script>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{E(title)}</title>
  <meta name="description" content="{E(description)}">
  <meta name="robots" content="{'noindex' if noindex else 'index, follow'}">
  <meta name="theme-color" content="#0B1F19">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="BCH Group">
  <meta property="og:locale" content="en_IE">
  <meta property="og:title" content="{E(title)}">
  <meta property="og:description" content="{E(description)}">
  <meta property="og:image" content="{photo_url('hero', root, 'images/hero.jpg')}">
  <meta name="twitter:card" content="summary_large_image">{canonical}
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%230a0a0a'/%3E%3Ctext x='32' y='42' font-family='Georgia,serif' font-size='26' font-weight='700' fill='%23c9a84c' text-anchor='middle'%3EBCH%3C/text%3E%3C/svg%3E">
  <link rel="apple-touch-icon" href="{photo_url('logo', root, 'images/logo-500.png', absolute=False)}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Instrument+Serif&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{root}{asset("css/style.css")}">
  <link rel="stylesheet" href="{root}{asset("css/pages.css")}">{ld}
</head>
<body class="subpage">

{nav(root, active=active)}

  <main>
{body}
  </main>

  {fix_root(MODAL, root)}

  {FAB}

{footer(root)}

  {config_script(root)}
  <script src="{root}{asset("js/places.js")}"></script>
  <script src="{root}{asset("js/main.js")}"></script>{extra_js}
</body>
</html>
"""


def local_photo(rel):
    """A site image path if that file exists, else None (so pages never link a
    missing photo and fall back to a plain dark panel)."""
    return rel if rel and (ROOT_DIR / rel).is_file() else None


def page_hero(root, crumbs, h1, lead, extra="", photo=None, split=False, slot_photo=None,
              overlap="", crumbs_below=False):
    """Page header. With a photo it is a full-bleed photo header with a
    directional gradient behind the text. `overlap` (a form bar) sits across
    the bottom edge. Breadcrumbs only show on deep pages (`crumbs_below`),
    as a small line under the header; the JSON-LD breadcrumb stays on every page.
    `split` is accepted for older callers and no longer changes the layout."""
    text = f"""      <h1>{h1}</h1>
      <p class="page-lead">{lead}</p>{extra}"""
    below = ""
    if crumbs_below:
        trail = " <span>/</span> ".join(
            f'<a href="{href}">{E(name)}</a>' if href else f'<span aria-current="page">{E(name)}</span>'
            for name, href in crumbs)
        below = f'\n    <nav class="crumbs crumbs-below" aria-label="Breadcrumb">{trail}</nav>'
    over = f'\n      <div class="hero-overlap">{overlap}\n      </div>' if overlap else ""
    photo = slot_photo or local_photo(photo)
    if not photo:
        return f"""    <section class="page-hero">
{text}
    </section>{below}"""
    return f"""    <section class="page-hero page-hero-photo{' has-overlap' if overlap else ''}">
      <div class="page-hero-frame">
        <img class="page-hero-img" src="{E(root + photo)}" alt="">
        <div class="page-hero-text">
{text}
        </div>
      </div>{over}
    </section>{below}"""


def breadcrumb_ld(crumbs):
    items = []
    for i, (name, href) in enumerate(crumbs, 1):
        item = {"@type": "ListItem", "position": i, "name": name}
        if SITE_URL and href is not None:
            item["item"] = SITE_URL.rstrip("/") + "/" + href
        items.append(item)
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items}


# ── Components ───────────────────────────────────────────────────────────────

def price_attr(t):
    """Value for data-price: whole euros, or empty when the price is unset."""
    return "" if t["price"] is None else str(t["price"])


def price_html(t, note=""):
    """Price block contents: 'From €X per vehicle', or just 'Price on request'."""
    if t["price"] is None:
        return price_label(t) + (f"<span>{note}</span>" if note else "")
    return f"<small>From</small>{price_label(t)}<span>{price_unit(t)}{', ' + note if note else ''}</span>"


def tour_card(t, root):
    """Compact card: photo (if any), name, region, duration, price and one Book button."""
    photo = tour_photo(t, root) + "\n        " if t["slug"] in TOUR_PHOTO else ""
    return f"""      <article class="tour-card{' has-photo' if photo else ''}" data-kind="{t['kind']}">
        {photo}<div class="tour-body">
          <h3><a href="{root}tours/{t['slug']}.html">{E(t['name'])}</a></h3>
          <p class="tour-meta">{E(t['region'])}<br>{E(t['duration'])}</p>
          <p class="tour-desc">{E(t['desc'])}</p>
        </div>
        <div class="tour-foot">
          <div class="tour-price">{price_html(t)}</div>
          <button type="button" class="btn btn-quiet tour-book" data-price="{price_attr(t)}" data-unit="{price_unit(t)}" data-tour="{E(t['name'])}">Book</button>
        </div>
      </article>"""


def multi_card(m, root):
    days = "".join(f"<li><strong>Day {i}</strong>{E(d)}</li>" for i, d in enumerate(m["plan"], 1))
    return f"""      <article class="multi-card" id="{m['slug']}">
        <div class="multi-head">
          <p class="tour-meta">{m['days']}-day sample route</p>
          <h3>{E(m['name'])}</h3>
          <p>{E(m['summary'])}</p>
        </div>
        <ol class="multi-days">{days}</ol>
        <div class="tour-foot">
          <div class="tour-price"><small>From</small>{eur(multi_price(m))}<span>{m['days']} days × {eur(MULTI_DAY_RATE)} per vehicle</span></div>
          <button type="button" class="btn btn-quiet tour-book" data-price="{multi_price(m)}" data-tour="{E(m['name'])} ({m['days']}-day tour)">Book</button>
        </div>
      </article>"""


def cta_band(root, title_key="cta.title", text_key="cta.text"):
    return f"""    <section class="cta-band">
      <div class="cta-inner">
        <div>
          <h2>{T(title_key)}</h2>
          <p>{T(text_key)}</p>
        </div>
        <div class="cta-actions">
          <a href="{root}index.html#booking" class="btn btn-primary">Book a taxi or tour</a>
          <a href="{E(WHATSAPP)}" class="btn btn-quiet" target="_blank" rel="noopener">WhatsApp</a>
          <a href="tel:{E(PHONE)}" class="btn btn-quiet">Call {E(PHONE_DISPLAY)}</a>
        </div>
      </div>
    </section>"""


def group_service():
    """Booking-form service name for groups bigger than one vehicle."""
    return f"Group transport ({MAX_PASSENGERS + 1}+)"


def count_word(n):
    words = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
             "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
             "Sixteen", "Seventeen", "Eighteen", "Nineteen", "Twenty"]
    return words[n] if n < len(words) else str(n)


def sample_names(tours, n=4):
    """Names of up to n tours (favourites first) for meta descriptions."""
    ordered = [t for t in tours if t["fav"]] + [t for t in tours if not t["fav"]]
    return [t["name"] for t in ordered[:n]]


# ── Pages ────────────────────────────────────────────────────────────────────

def build_tour_pages():
    out = {}
    for t in TOURS:
        root = "../"
        kind = t["kind"]
        listing, list_name, active = KIND_PAGE[kind]
        suffix = KIND_SUFFIX[kind]
        unit = price_unit(t)
        crumbs = [("Home", "index.html"), (list_name, listing), (t["name"], None)]
        same_kind = [o for o in published(kind) if o["slug"] != t["slug"]]
        if kind == "day":
            others = [o for o in same_kind if o["area"] == t["area"]]
            others += [o for o in same_kind if o["fav"] and o not in others]
        else:
            others = same_kind
        detail_photo = (tour_photo(t, root, "tour-photo tour-photo-lg", lazy=False) + "\n          "
                        if t["slug"] in TOUR_PHOTO else "")
        hl = "".join(f"<li>{E(x)}</li>" for x in t["highlights"])
        inc = "".join(f"<li>{x}</li>" for x in T_lines(f"included.{kind}"))
        calc_link = (f'\n          <a class="book-alt" href="{root}price-calculator.html?tour={t["slug"]}">Add extras in the price calculator</a>'
                     if kind == "day" and t["price"] is not None else "")
        also = "\n".join(tour_card(o, root) for o in others[:3])
        more = f"""
    <section class="section section-mist">
      <div class="wrap">
        <h2>{T("tour.more_title")}</h2>
        <div class="tours-grid">
{also}
        </div>
      </div>
    </section>
""" if also else ""
        body = page_hero(root, [(n, (root + h) if h else None) for n, h in crumbs],
                         E(t["name"]) + " " + suffix.lower(),
                         E(t["desc"]), crumbs_below=True) + f"""

    <section class="section tour-detail">
      <div class="wrap detail-grid">
        <aside class="book-card">
          <div class="tour-price">{price_html(t, f"up to {MAX_PASSENGERS} people")}</div>
          <ul class="book-facts">
            <li><span>Duration</span>{E(t['duration'])}</li>
            <li><span>Drive from Dublin</span>{E(t['drive'])}</li>
            <li><span>Group size</span>Up to {MAX_PASSENGERS} passengers</li>
            <li><span>Pickup</span>Dublin or Meath</li>
          </ul>
          <button type="button" class="btn btn-primary tour-book" data-price="{price_attr(t)}" data-unit="{unit}" data-tour="{E(t['name'])}">Book this tour</button>
          <a class="btn btn-quiet" href="{E(WHATSAPP)}?text={quote(f"Hi BCH Group, I'd like to ask about the {t['name']} tour.")}" target="_blank" rel="noopener">Ask on WhatsApp</a>{calc_link}
          <p class="book-group">More than {MAX_PASSENGERS} people? <a href="{root}index.html?service={quote(group_service(), safe='()')}#booking">We can arrange extra vehicles.</a></p>
        </aside>
        <div class="detail-main">
          {detail_photo}<h2>{T("tour.about_title")}</h2>
          <p>{E(t['intro'])}</p>
          <h2>{T("tour.highlights_title")}</h2>
          <ul class="check-list">{hl}</ul>
          <h2>{T("tour.included_title")}</h2>
          <ul class="check-list">{inc}</ul>
          <h2>{T("tour.good_title")}</h2>
          <p>{T(f"good_to_know.{kind}")}</p>
        </div>
      </div>
    </section>
{more}
{cta_band(root)}"""
        tour_ld = {
            "@context": "https://schema.org", "@type": "TouristTrip",
            "name": f"{t['name']} {suffix}", "description": t["desc"],
            "touristType": "Private group",
            "itinerary": {"@type": "ItemList", "itemListElement": [
                {"@type": "ListItem", "position": i, "name": h} for i, h in enumerate(t["highlights"], 1)]},
            "provider": {"@type": "TaxiService", "name": "BCH Group", "telephone": PHONE},
        }
        if t["price"] is not None:
            tour_ld["offers"] = {"@type": "Offer", "price": t["price"], "priceCurrency": "EUR",
                                 "description": f"{unit.capitalize()}, up to {MAX_PASSENGERS} passengers"}
        ld = [tour_ld, breadcrumb_ld([("Home", ""), (list_name, listing), (t["name"], f"tours/{t['slug']}.html")])]
        unit_title = "per " + unit[4:].capitalize()
        origin = " from Dublin" if kind == "day" else ""
        title = f"{t['name']} {suffix}{origin}"
        if t["price"] is not None:
            title += f" | {price_label(t)} {unit_title}"
        title += " | BCH Group"
        if kind == "day":
            desc = f"Private {t['name']} day tour from Dublin or Meath in a wheelchair-accessible 8-seater. {t['duration']}"
        else:
            desc = f"Private {t['name']} {KIND_NOUN[kind]} in a wheelchair-accessible 8-seater. {t['duration']}"
        desc += (f", from {price_label(t)} {unit} for up to {MAX_PASSENGERS} people." if t["price"] is not None
                 else f", for up to {MAX_PASSENGERS} people.")
        out[f"tours/{t['slug']}.html"] = page(
            root=root, active=active, path=f"tours/{t['slug']}.html", jsonld=ld,
            title=title, description=desc, body=body, noindex=not t["published"])
    return out


def build_kind_listing(kind, title):
    """Pub Tours / Golf Trips listing page."""
    root = ""
    listing, list_name, active = KIND_PAGE[kind]
    tours = published(kind)
    cards = "\n".join(tour_card(t, root) for t in tours) if tours else \
        f'      <p class="tours-note">{T(kind + ".empty")}</p>'
    inc = "".join(f"<li>{x}</li>" for x in T_lines(f"included.{kind}"))
    body = page_hero(root, [("Home", "index.html"), (list_name, None)],
                     T(kind + ".title"), T(kind + ".lead"), photo=f"images/band-{kind}.jpg") + f"""

    <section class="section">
      <div class="wrap">
        <div class="tours-grid">
{cards}
        </div>
        <div class="note-box">
          <h2>{T("tour.included_title")}</h2>
          <ul class="check-list">{inc}</ul>
        </div>
      </div>
    </section>

{cta_band(root, kind + ".cta_title", kind + ".cta_text")}"""
    return {listing: page(
        root=root, active=active, path=listing,
        jsonld=[breadcrumb_ld([("Home", ""), (list_name, listing)])],
        title=title, description=texts.raw(kind + ".description"), body=body)}


def build_pub_tours():
    return build_kind_listing("pub", "Rural Pub Tours from Dublin & Meath | BCH Group")


def build_golf_trips():
    return build_kind_listing("golf", "Golf Trips from Dublin & Meath | BCH Group")


def build_tours_hub():
    root = ""
    crumbs = [("Home", "index.html"), ("Tours", None)]
    day = published("day")
    n = len(day)
    lead_count = f"{count_word(n)} full-day private tours" if n else "Full-day private tours"
    body = page_hero(root, crumbs, T("tours.title"),
                     f"{lead_count} {T('tours.lead')}", photo="images/band-tours.jpg") + f"""

    <section class="section">
      <div class="wrap">
        <div class="tours-grid">
{chr(10).join(tour_card(t, root) for t in day)}
        </div>
        <div class="split-promo">
          <div>
            <h2>{T("tours.multi_title")}</h2>
            <p>{T("tours.multi_before")} {eur(MULTI_DAY_RATE)} {T("tours.multi_after")}</p>
          </div>
          <div class="promo-actions">
            <a href="multi-day-tours.html" class="btn btn-quiet">See multi-day tours</a>
            <a href="destinations.html" class="link-strong">Destination guide</a>
          </div>
        </div>
      </div>
    </section>

{cta_band(root)}"""
    return {"tours.html": page(
        root=root, active="tours", path="tours.html", jsonld=[breadcrumb_ld([("Home", ""), ("Tours", "tours.html")])],
        title="Private Day Tours of Ireland from Dublin | BCH Group",
        description=(f"{n} private day tours from Dublin and Meath: " if n else "Private day tours from Dublin and Meath: ")
        + (", ".join(sample_names(day)) + " and more. " if n else "")
        + f"Per-vehicle prices for up to {MAX_PASSENGERS} people.",
        body=body)}


def build_multi_day():
    root = ""
    crumbs = [("Home", "index.html"), ("Multi-day tours", None)]
    notes = "".join(f"\n          <li>{x}</li>" for x in T_lines("multi.notes"))
    body = page_hero(root, crumbs, T("multi.title"),
                     f"{T('multi.lead_before')} {eur(MULTI_DAY_RATE)} {T('multi.lead_after')}", photo="images/hero.jpg") + f"""

    <section class="section">
      <div class="wrap">
        <div class="multi-grid">
{chr(10).join(multi_card(m, root) for m in MULTI_DAY)}
        </div>
        <div class="note-box">
          <h2>{T("multi.notes_title")}</h2>
          <ul class="check-list">
            <li>{eur(MULTI_DAY_RATE)} {T("multi.note_rate")}</li>{notes}
          </ul>
          <a href="price-calculator.html" class="btn btn-quiet">Price a custom trip</a>
        </div>
      </div>
    </section>

{cta_band(root, "multi.cta_title", "multi.cta_text")}"""
    return {"multi-day-tours.html": page(
        root=root, active="multi", path="multi-day-tours.html",
        jsonld=[breadcrumb_ld([("Home", ""), ("Multi-day tours", "multi-day-tours.html")])],
        title="Multi-Day Private Tours of Ireland | BCH Group",
        description=f"Private multi-day tours of Ireland with your own driver, from {eur(MULTI_DAY_RATE)} per day for up to {MAX_PASSENGERS} people. Sample routes: West Coast, Kerry, Causeway Coast and the Wild Atlantic Way.",
        body=body)}


def build_calculator():
    root = ""
    crumbs = [("Home", "index.html"), ("Price calculator", None)]
    calc_tours = [t for t in published("day") if t["price"] is not None]
    data = {
        "tours": [{"slug": t["slug"], "name": t["name"], "price": t["price"]} for t in calc_tours],
        "multi": [{"slug": m["slug"], "name": m["name"], "days": m["days"]} for m in MULTI_DAY],
        "dayRate": MULTI_DAY_RATE, "hourRate": EXTRA_HOUR_RATE, "maxPax": MAX_PASSENGERS,
        "airport": [{"area": a, "to": to, "from": fr} for a, _, to, fr in AIRPORT_FARES]
                   + [{"area": a, "to": p, "from": p} for a, p in LONG_TRANSFERS],
    }
    tour_opts = "".join(f'<option value="{t["slug"]}">{E(t["name"])} ({eur(t["price"])})</option>' for t in calc_tours)
    multi_opts = "".join(f'<option value="{m["slug"]}">{E(m["name"])} ({m["days"]} days)</option>' for m in MULTI_DAY)
    air_opts = "".join(f'<option value="{i}">{E(a["area"])}</option>' for i, a in enumerate(data["airport"]))
    dial = re.search(r'<select name="dial".*?</select>', MODAL, re.S).group(0)
    body = page_hero(root, crumbs, T("calc.title"), T("calc.lead")) + f"""

    <section class="section calc-section">
      <form class="calc" id="calc-form" novalidate>
        <div class="calc-main">
          <div class="calc-row">
            <div class="calc-row-head"><span class="calc-num">1</span><div><h3>Day tour</h3><p>{T("calc.row1_desc")}</p></div></div>
            <select id="calc-tour" name="tour" aria-label="Day tour"><option value="">No day tour</option>{tour_opts}</select>
          </div>
          <div class="calc-row">
            <div class="calc-row-head"><span class="calc-num">2</span><div><h3>Multi-day tour</h3><p>{T("calc.row2_before")} {eur(MULTI_DAY_RATE)} {T("calc.row2_after")}</p></div></div>
            <div class="calc-inline">
              <select id="calc-multi" name="multi" aria-label="Multi-day tour"><option value="">No multi-day tour</option>{multi_opts}<option value="custom">Custom route</option></select>
              <div class="stepper calc-days" hidden>
                <button type="button" data-step="-1" aria-label="Fewer days">−</button>
                <input id="calc-days" name="days" type="number" value="2" min="2" max="21" readonly aria-label="Days">
                <button type="button" data-step="1" aria-label="More days">+</button>
                <span class="stepper-unit">days</span>
              </div>
            </div>
          </div>
          <div class="calc-row">
            <div class="calc-row-head"><span class="calc-num">3</span><div><h3>Airport transfer</h3><p>{T("calc.row3_desc")}</p></div></div>
            <div class="calc-inline">
              <select id="calc-air" name="air" aria-label="Airport transfer area"><option value="">No airport transfer</option>{air_opts}</select>
              <select id="calc-dir" name="dir" aria-label="Direction" hidden>
                <option value="to">To the airport</option>
                <option value="from">From the airport</option>
                <option value="both">Both ways</option>
              </select>
            </div>
          </div>
          <div class="calc-row">
            <div class="calc-row-head"><span class="calc-num">4</span><div><h3>Extra hours</h3><p>{T("calc.row4_before")} {eur(EXTRA_HOUR_RATE)} {T("calc.row4_after")}</p></div></div>
            <div class="stepper">
              <button type="button" data-step="-1" aria-label="Fewer hours">−</button>
              <input id="calc-hours" name="hours" type="number" value="0" min="0" max="12" readonly aria-label="Extra hours">
              <button type="button" data-step="1" aria-label="More hours">+</button>
              <span class="stepper-unit">hours</span>
            </div>
          </div>
          <div class="calc-row">
            <div class="calc-row-head"><span class="calc-num">5</span><div><h3>Passengers</h3><p>{T("calc.row5_before")} {MAX_PASSENGERS} {T("calc.row5_after")}</p><p class="pax-more" hidden>More than {MAX_PASSENGERS}? We can arrange extra vehicles. Add your group size in the notes for a group quote.</p></div></div>
            <div class="stepper">
              <button type="button" data-step="-1" aria-label="Fewer passengers">−</button>
              <input id="calc-pax" name="passengers" type="number" value="2" min="1" max="{MAX_PASSENGERS}" readonly aria-label="Passengers">
              <button type="button" data-step="1" aria-label="More passengers">+</button>
              <span class="stepper-unit">people</span>
            </div>
          </div>
        </div>

        <aside class="calc-quote">
          <h3>Your estimated quote</h3>
          <ul class="calc-lines" id="calc-lines"><li class="calc-empty">Choose a tour, trip or transfer to see your price.</li></ul>
          <div class="calc-total"><span>Total</span><strong id="calc-total">–</strong></div>
          <p class="calc-pp" id="calc-pp"></p>
          <div class="calc-request">
            <h4>Send me this quote</h4>
            <div class="form-field"><label for="calc-name">Full name</label><input id="calc-name" name="name" type="text" autocomplete="name" required data-label="Name"></div>
            <div class="form-field"><label for="calc-email">Email</label><input id="calc-email" name="email" type="email" autocomplete="email" required data-label="Email"></div>
            <div class="form-field"><label for="calc-phone">Phone</label><div class="phone-row">{dial}<input id="calc-phone" name="phone" type="tel" autocomplete="tel-national" required data-label="Phone"></div></div>
            <div class="form-field"><label for="calc-date">Travel date</label><input id="calc-date" name="date" type="date" data-label="Travel date"></div>
            <div class="form-field"><label for="calc-notes">Notes</label><textarea id="calc-notes" name="notes" rows="3" placeholder="Pickup area, special requests…" data-label="Notes"></textarea></div>
            <input class="form-honey" type="text" name="_honey" tabindex="-1" autocomplete="off" aria-hidden="true">
            <button type="submit" class="btn btn-primary btn-wide" id="calc-send"><span class="send-label">Request a fixed quote</span></button>
            <button type="button" class="btn btn-quiet btn-wide" id="calc-wa">Send on WhatsApp</button>
            <p class="form-status" id="calc-status" role="status" aria-live="polite"></p>
            <p class="form-legal">{T("calc.legal")}</p>
          </div>
        </aside>
      </form>
      <script id="calc-data" type="application/json">{_ld_dumps(data)}</script>
    </section>

    <section class="section section-mist">
      <div class="wrap">
        <h2>{T("calc.how_title")}</h2>
        <ol class="steps-list">
          <li><strong>{T("calc.step1_title")}</strong> {T("calc.step1_text")}</li>
          <li><strong>{T("calc.step2_title")}</strong> {T("calc.step2_text")}</li>
          <li><strong>{T("calc.step3_title")}</strong> {T("calc.step3_text")}</li>
          <li><strong>{T("calc.step4_title")}</strong> {T("calc.step4_text")}</li>
        </ol>
      </div>
    </section>"""
    return {"price-calculator.html": page(
        root=root, active="prices", path="price-calculator.html",
        jsonld=[breadcrumb_ld([("Home", ""), ("Price calculator", "price-calculator.html")])],
        title="Tour & Taxi Price Calculator | Instant Quote | BCH Group",
        description=f"Work out the price of your Ireland day tour, multi-day trip or Dublin Airport transfer instantly. Per-vehicle prices for up to {MAX_PASSENGERS} passengers.",
        body=body, extra_js=f'\n  <script src="{root}{asset("js/calculator.js")}"></script>')}


def build_destinations():
    root = ""
    crumbs = [("Home", "index.html"), ("Destinations", None)]
    groups = []
    for area in AREAS:
        items = [t for t in published("day") if t["area"] == area]
        if not items:
            continue
        cards = "\n".join(f"""        <a class="dest-card" href="tours/{t['slug']}.html">
          <span class="tour-region">{E(t['region'])}</span>
          <h3>{E(t['name'])}</h3>
          <p>{E(t['desc'])}</p>
          <span class="dest-meta"><span>From Dublin: {E(t['drive'])}</span><strong>{price_label(t)}</strong></span>
        </a>""" for t in items)
        groups.append(f"""      <div class="dest-group">
        <h2 class="dest-area">{E(area)}</h2>
        <div class="dest-grid">
{cards}
        </div>
      </div>""")
    body = page_hero(root, crumbs, T("dest.title"), T("dest.lead")) + f"""

    <section class="section">
      <div class="wrap">
{chr(10).join(groups)}
        <p class="tours-note">{T("dest.note_before")} <a href="index.html#booking">Ask us</a>{T("dest.note_after")}</p>
      </div>
    </section>

{cta_band(root)}"""
    return {"destinations.html": page(
        root=root, active="tours", path="destinations.html",
        jsonld=[breadcrumb_ld([("Home", ""), ("Destinations", "destinations.html")])],
        title="Ireland Destination Guide: Day Trips & Driving Times from Dublin | BCH Group",
        description="Where to go in Ireland and how far it is from Dublin: "
        + ", ".join(sample_names(published("day"), 5)) + " and more, with private tour prices.",
        body=body)}


def fmt_date(d):
    import datetime
    return datetime.date.fromisoformat(d).strftime("%-d %B %Y")


def post_body(body, root):
    """Post HTML with {ROOT} filled and links to renamed tours repointed."""
    def fix(m):
        slug = m.group(1)
        return m.group(0) if slug in TOUR_BY_SLUG else f"tours/{resolve_redirect(slug, REDIRECTS)}.html"
    body = re.sub(r"tours/([a-z0-9-]+)\.html", fix, body).replace("{ROOT}", root)
    return texts.dyn(body)   # posts are code, so the built-in passenger limit applies


def build_blog():
    out = {}
    root = ""
    cards = "\n".join(f"""        <a class="post-card" href="blog/{p['slug']}.html">
          <span class="tour-region">{E(p['topic'])}</span>
          <h3>{E(p['title'])}</h3>
          <p>{E(p['summary'])}</p>
          <span class="post-meta">{fmt_date(p['date'])}</span>
        </a>""" for p in POSTS)
    body = page_hero(root, [("Home", "index.html"), ("Blog", None)], T("blog.title"), T("blog.lead")) + f"""

    <section class="section">
      <div class="wrap post-grid">
{cards}
      </div>
    </section>

{cta_band(root)}"""
    out["blog.html"] = page(root=root, active="blog", path="blog.html",
                            jsonld=[breadcrumb_ld([("Home", ""), ("Blog", "blog.html")])],
                            title="Ireland Travel Guides & Taxi Tips | BCH Group Blog",
                            description="Practical guides to day trips from Dublin, Dublin Airport transfers, accessible travel and planning a road trip around Ireland.",
                            body=body)

    for p in POSTS:
        root = "../"
        others = [o for o in POSTS if o["slug"] != p["slug"]][:3]
        more = "\n".join(f"""        <a class="post-card" href="{o['slug']}.html">
          <span class="tour-region">{E(o['topic'])}</span>
          <h3>{E(o['title'])}</h3>
          <p>{E(o['summary'])}</p>
        </a>""" for o in others)
        body = page_hero(root, [("Home", root + "index.html"), ("Blog", root + "blog.html"), (p["title"], None)],
                         E(p["title"]), E(p["summary"]),
                         f'\n      <p class="hero-meta">{fmt_date(p["date"])}</p>', crumbs_below=True) + f"""

    <section class="section">
      <article class="post-body">
{post_body(p['body'], root)}
      </article>
    </section>

    <section class="section section-mist">
      <div class="wrap">
        <h2>More travel guides</h2>
        <div class="post-grid">
{more}
        </div>
      </div>
    </section>

{cta_band(root)}"""
        ld = [{
            "@context": "https://schema.org", "@type": "BlogPosting",
            "headline": p["title"], "description": p["summary"], "datePublished": p["date"],
            "author": {"@type": "Organization", "name": "BCH Group"},
            "publisher": {"@type": "Organization", "name": "BCH Group"},
        }, breadcrumb_ld([("Home", ""), ("Blog", "blog.html"), (p["title"], f"blog/{p['slug']}.html")])]
        out[f"blog/{p['slug']}.html"] = page(root=root, active="blog", path=f"blog/{p['slug']}.html", jsonld=ld,
                                             title=f"{p['title']} | BCH Group", description=p["summary"], body=body)
    return out


# ── Fleet, business, partners, help ──────────────────────────────────────────

def fleet_published():
    return [v for v in FLEET if v.get("published")]


def vehicle_image(v, root):
    """Site path for a vehicle photo: the admin photo if set, else
    images/fleet-<slug>.jpg if that file exists, else "" (a name panel)."""
    path = VEHICLE_PHOTO.get(v["slug"])
    if not path and isinstance(v["slug"], str) and _SLUG_RE.match(v["slug"]):
        rel = f"images/fleet-{v['slug']}.jpg"
        if (ROOT_DIR / rel).is_file():
            path = rel
    return root + path if path else ""


def vehicle_media(v, root, cls="tour-photo"):
    src = vehicle_image(v, root)
    if src:
        return f'<img class="{cls}" src="{E(src)}" alt="{E(v["name"])}" loading="lazy">'
    return f'<div class="fleet-panel" aria-hidden="true"><span>{E(v["name"])}</span></div>'


ICON_SEAT = ('<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="7" r="4"/>'
             '<path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1"/></svg>')
ICON_BAG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="7" width="16" height="13" rx="2"/>'
            '<path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M9 20v1M15 20v1"/></svg>')


def vehicle_specs(v):
    """Seats and bags as small icon + number pairs."""
    items = [f'<li>{ICON_SEAT}<b>{v["passengers"]}</b> seats</li>']
    if v["bags"]:
        items.append(f'<li>{ICON_BAG}<b>{v["bags"]}</b> bags</li>')
    return '<ul class="specs">' + "".join(items) + "</ul>"


def vehicle_card(v, root):
    """Fleet page: one full-width spec sheet per vehicle."""
    feats = "".join(f"<li>{E(f)}</li>" for f in v["features"])
    example = f'<p class="tour-meta">{E(v["example"])}</p>' if v["example"] else ""
    desc = f'<p class="tour-desc">{E(v["desc"])}</p>' if v["desc"] else ""
    feat_list = f'<ul class="check-list">{feats}</ul>' if feats else ""
    return f"""      <article class="fleet-sheet fleet-card" id="{E(v['slug'])}">
        <div class="fleet-sheet-media">{vehicle_media(v, root)}</div>
        <div class="fleet-sheet-body">
          <h2>{E(v['name'])}</h2>
          {example}
          {desc}
          {vehicle_spec_grid(v)}
          {feat_list}
          <a class="btn btn-primary" href="{root}index.html?vehicle={quote(v['slug'])}#booking">{T("fleet.book_button")}</a>
        </div>
      </article>"""


def vehicle_mini(v, root):
    return f"""        <a class="fleet-mini" href="{root}fleet.html">
          {vehicle_media(v, root, "mini-img")}
          <strong>{E(v['name'])}</strong>
          {vehicle_specs(v)}
        </a>"""


def build_fleet():
    root = ""
    vehicles = fleet_published()
    cards = "\n".join(vehicle_card(v, root) for v in vehicles) if vehicles else \
        f'      <p class="tours-note">{T("fleet.empty")}</p>'
    fleet_faq, fleet_ld = faq_block("fleet", 4, "fleet.faq_title")
    body = page_hero(root, [("Home", "index.html"), ("Fleet", None)],
                     T("fleet.title"), T("fleet.lead"), photo="images/hero.jpg") + f"""

    <section class="section">
      <div class="wrap">
        <div class="fleet-grid fleet-sheets">
{cards}
        </div>
      </div>
    </section>

{fleet_faq}

{cta_band(root, "fleet.cta_title", "fleet.cta_text")}"""
    return {"fleet.html": page(
        root=root, active="fleet", path="fleet.html",
        jsonld=[breadcrumb_ld([("Home", ""), ("Fleet", "fleet.html")]), fleet_ld],
        title="Our Fleet: Saloon, MPV, 8-Seater Van & Minibus | BCH Group",
        description=texts.raw("fleet.description"), body=body)}


def enquiry_form(form_id, *, subject, subject_field, kind, fields, button_key, legal_key):
    """A FormSubmit enquiry form (sent by js/main.js). `fields` is a list of
    (name, label, type, required, extra) with type text/email/tel/textarea/select."""
    dial = re.search(r'<select name="dial".*?</select>', MODAL, re.S).group(0)
    rows = []
    for name, label, typ, req, extra in fields:
        fid = f"{form_id}-{name}"
        r = " required" if req else ""
        lab = f'<label for="{fid}">{label}{"" if req else " (optional)"}</label>'
        if typ == "textarea":
            ctl = f'<textarea id="{fid}" name="{name}" rows="3" data-label="{label}"></textarea>'
        elif typ == "select":
            opts = "".join(f"<option>{o}</option>" for o in extra)
            ctl = f'<select id="{fid}" name="{name}"{r} data-label="{label}">{opts}</select>'
        elif typ == "tel":
            ctl = (f'<div class="phone-row">{dial}<input id="{fid}" name="{name}" type="tel" '
                   f'autocomplete="tel-national"{r} data-label="{label}"></div>')
        else:
            ac = f' autocomplete="{extra}"' if extra else ""
            ctl = f'<input id="{fid}" name="{name}" type="{typ}"{ac}{r} data-label="{label}">'
        rows.append(f'        <div class="form-field">{lab}{ctl}</div>')
    return f"""      <form class="enquiry" id="{form_id}" novalidate data-subject="{E(subject)}" data-subject-field="{subject_field}" data-enquiry="{E(kind)}">
{chr(10).join(rows)}
        <input class="form-honey" type="text" name="_honey" tabindex="-1" autocomplete="off" aria-hidden="true">
        <button type="submit" class="btn btn-primary btn-wide"><span class="send-label">{T(button_key)}</span></button>
        <p class="form-status" role="status" aria-live="polite"></p>
        <p class="form-legal">{T(legal_key)}</p>
      </form>"""


def _list(items):
    return "".join(f"<li>{x}</li>" for x in items)


# ── Shared page sections (business, partners, fleet, help) ─────────────────

def book_link(root, service, topic=""):
    """Homepage booking card with the service (and an optional topic for the
    notes) filled in."""
    q = f"service={quote(service, safe='()/')}"
    if topic:
        q += f"&topic={quote(topic)}"
    return f"{root}index.html?{q}#booking"


SVC_ICONS = {
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "briefcase": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6"/>',
    "school": '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c2 2 10 2 12 0v-5"/>',
}


def service_cards(root, prefix, items, button_key):
    """Photo cards with a title, one or two lines and a Book now button.
    `items` is a list of (key, photo or None, service, extra_html, icon). A card
    without a photo file is a compact icon card (no empty photo area)."""
    cards = []
    for key, photo, service, extra, icon in items:
        img = local_photo(photo)
        media = (f'<img class="svc-img" src="{root}{img}" alt="" loading="lazy">' if img
                 else f'<span class="svc-icon" aria-hidden="true"><svg viewBox="0 0 24 24">{SVC_ICONS.get(icon, SVC_ICONS["briefcase"])}</svg></span>')
        title = texts.raw(f"{prefix}.{key}_title")
        cards.append(f"""        <article class="svc-card{'' if img else ' no-photo'}">
          {media}
          <div class="svc-body">
            <h3>{T(f"{prefix}.{key}_title")}</h3>
            <p>{T(f"{prefix}.{key}_text")}</p>{extra}
            <a class="btn btn-primary" href="{E(book_link(root, service, title))}">{T(button_key)}</a>
          </div>
        </article>""")
    photo_cards = [c for c in cards if 'class="svc-img"' in c]
    icon_cards = [c for c in cards if 'class="svc-img"' not in c]
    out = ""
    if photo_cards:
        out += '      <div class="svc-grid">\n' + "\n".join(photo_cards) + "\n      </div>"
    if icon_cards:
        out += '\n      <div class="svc-mini-grid">\n' + "\n".join(icon_cards) + "\n      </div>"
    return out


def promise_tiles(prefix, n=3):
    return "\n".join(f'          <div class="tile tile-promise"><h3>{T(f"{prefix}.p{i}_title")}</h3><p>{T(f"{prefix}.p{i}_text")}</p></div>'
                     for i in range(1, n + 1))


def faq_block(prefix, n, title_key):
    """Accordion of <prefix>.faq_q<i> / faq_a<i> plus its FAQPage JSON-LD."""
    pairs = [(f"{prefix}.faq_q{i}", f"{prefix}.faq_a{i}") for i in range(1, n + 1)
             if texts.raw(f"{prefix}.faq_q{i}").strip()]
    items = "\n".join(f'          <details class="faq-item"><summary>{T(q)}</summary><p>{T(a)}</p></details>'
                      for q, a in pairs)
    html = f"""    <section class="section section-alt" id="faq">
      <div class="wrap faq-split">
        <h2>{T(title_key)}</h2>
        <div class="faq-list">
{items}
        </div>
      </div>
    </section>"""
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": texts.raw(q),
         "acceptedAnswer": {"@type": "Answer", "text": texts.raw(a)}} for q, a in pairs]}
    return html, ld


def booking_bar(root, service, title_key, button_key):
    """Compact quote bar: sends date, from and to to the homepage booking card."""
    return f"""
      <form class="quote-bar" action="{root}index.html#booking" method="get">
        <input type="hidden" name="service" value="{E(service)}">
        <p class="quote-bar-title">{T(title_key)}</p>
        <div class="quote-bar-fields">
          <div class="field"><label for="qb-date">Date</label><input id="qb-date" name="date" type="date"></div>
          <div class="field"><label for="qb-from">From</label><input id="qb-from" name="pickup" type="text" placeholder="Add pickup" data-places></div>
          <div class="field"><label for="qb-to">To</label><input id="qb-to" name="destination" type="text" placeholder="Add drop-off" data-places></div>
          <button type="submit" class="btn btn-primary"><span>{T(button_key)}</span><span class="i-arrow" aria-hidden="true"></span></button>
        </div>
      </form>"""


def vehicle_grid(root):
    """Compact vehicle cards (photo, name, seats and bags) linking to the fleet page."""
    vehicles = fleet_published()
    if not vehicles:
        return f'      <p class="tours-note">{T("fleet.empty")}</p>'
    return ('      <div class="fleet-strip-grid">\n'
            + "\n".join(vehicle_mini(v, root) for v in vehicles) + "\n      </div>")


def build_business():
    root = ""
    corp = "Corporate / business"
    intercity = " ".join(f"{E(a)} {eur(p)}." for a, p in LONG_TRANSFERS[:3])
    intercity = (f'\n            <p class="svc-prices">From Dublin Airport: {intercity}</p>' if intercity else "")
    chauffeur = service_cards(root, "business", [
        ("c1", "images/band-airport.jpg", "Airport transfer", "", None),
        ("c2", None, corp, "", "clock"),
        ("c3", "images/hero.jpg", corp, "", None),
        ("c4", "images/photo-events.jpg", corp, "", None),
        ("c5", "images/photo-intercity.jpg", "Point-to-point", intercity, None),
    ], "business.book_button")
    crew = service_cards(root, "business", [
        ("e1", "images/photo-crew.jpg", corp, "", None),
        ("e2", "images/photo-commute.jpg", corp, "", None),
        ("e3", None, corp, "", "clock"),
        ("e4", None, group_service(), "", "users"),
        ("e5", None, "School transport", "", "school"),
    ], "business.book_button")
    options = _list(T_lines("business.special_options"))
    form = enquiry_form(
        "biz-form", subject="New business account enquiry from", subject_field="company",
        kind="Business account", button_key="business.form_button", legal_key="business.form_legal",
        fields=[("name", "Your name", "text", True, "name"),
                ("company", "Company", "text", True, "organization"),
                ("email", "Email", "email", True, "email"),
                ("phone", "Phone", "tel", True, None),
                ("reference", "Your reference or PO number", "text", False, None),
                ("message", "What do you need?", "textarea", False, None)])
    faq, faq_ld = faq_block("business", 7, "business.faq_title")
    jumps = "".join(f'<li><a href="#{a}">{T(k)}</a></li>' for a, k in
                    (("chauffeur", "business.chauffeur_title"), ("crew", "business.crew_title"),
                     ("special", "business.special_title")))
    body = page_hero(root, [("Home", "index.html"), ("Business", None)],
                     T("business.title"), T("business.lead"),
                     overlap=booking_bar(root, corp, "business.bar_title", "business.bar_button"),
                     photo="images/photo-business.jpg") + f"""

    <section class="section offer">
      <div class="wrap">
        <div class="section-head">
          <h2>{T("business.offer_title")}</h2>
          <p>{T("business.offer_text")}</p>
          <ul class="jump-links">{jumps}</ul>
        </div>
        <div class="bento bento-offer">
          <div class="tile tile-lg">
            <h3>{T("business.built_title")}</h3>
            <p>{T("business.built_text")}</p>
            <ul class="check-list">{_list(T_lines("business.benefits"))}</ul>
          </div>
{promise_tiles("business")}
        </div>
      </div>
    </section>

    <section class="section section-alt" id="chauffeur">
      <div class="wrap">
        <div class="section-head"><h2>{T("business.chauffeur_title")}</h2><p>{T("business.chauffeur_text")}</p></div>
{chauffeur}
      </div>
    </section>

    <section class="section section-alt" id="crew">
      <div class="wrap">
        <div class="section-head"><h2>{T("business.crew_title")}</h2><p>{T("business.crew_text")}</p></div>
{crew}
      </div>
    </section>

    <section class="section" id="vehicles">
      <div class="wrap">
        <div class="section-head"><h2>{T("business.fleet_title")}</h2><p>{T("business.fleet_text")}</p></div>
{vehicle_grid(root)}
        <p class="tours-foot"><a class="link-strong" href="fleet.html">{T("business.fleet_link")}</a></p>
      </div>
    </section>

    <section class="section section-alt" id="special">
      <div class="wrap enquiry-grid">
        <div>
          <h2>{T("business.special_title")}</h2>
          <p class="lead-soft">{T("business.special_text")}</p>
          <ul class="check-list special-list">{options}</ul>
        </div>
        <div class="form-panel" id="account">
          <h2>{T("business.form_title")}</h2>
          <p class="form-lead">{T("business.form_lead")}</p>
{form}
        </div>
      </div>
    </section>

{faq}"""
    return {"business.html": page(
        root=root, active="business", path="business.html",
        jsonld=[breadcrumb_ld([("Home", ""), ("Business", "business.html")]), faq_ld],
        title="Business Travel, Chauffeur & Staff Transport | BCH Group",
        description=texts.raw("business.description"), body=body)}


def build_partners():
    root = ""
    form = enquiry_form(
        "partner-form", subject="New partner enquiry from", subject_field="business",
        kind="Partner", button_key="partners.form_button", legal_key="partners.form_legal",
        fields=[("business", "Business name", "text", True, "organization"),
                ("type", "Type of business", "select", True,
                 ["Hotel or guest house", "Travel agent", "Event planner", "Tour operator", "Other"]),
                ("name", "Your name", "text", True, "name"),
                ("email", "Email", "email", True, "email"),
                ("phone", "Phone", "tel", True, None),
                ("website", "Website", "text", False, "url"),
                ("notes", "Notes", "textarea", False, None)])
    steps = "".join(f"\n          <li><strong>{T(f'partners.step{n}_title')}</strong> {T(f'partners.step{n}_text')}</li>"
                    for n in (1, 2, 3))
    gets = "".join(f'\n          <div class="tile tile-promise"><h3>{x}</h3></div>' for x in T_lines("partners.gets"))
    faq, faq_ld = faq_block("partners", 3, "partners.faq_title")
    body = page_hero(root, [("Home", "index.html"), ("Partners", None)],
                     T("partners.title"), T("partners.lead"), photo="images/band-airport.jpg", split=True) + f"""

    <section class="section">
      <div class="wrap">
        <h2>{T("partners.gets_title")}</h2>
        <div class="bento bento-three">{gets}
        </div>
      </div>
    </section>

    <section class="section section-alt">
      <div class="wrap offer-grid">
        <div>
          <h2>{T("partners.who_title")}</h2>
          <ul class="check-list">{_list(T_lines("partners.who"))}</ul>
        </div>
        <div>
          <h2>{T("partners.how_title")}</h2>
          <ol class="steps-list steps-col">{steps}
          </ol>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="wrap">
        <div class="section-head"><h2>{T("fleet.title")}</h2><p>{T("business.fleet_text")}</p></div>
{vehicle_grid(root)}
      </div>
    </section>

    <section class="section section-alt" id="partner">
      <div class="wrap enquiry-grid">
        <div>
          <h2>{T("partners.form_title")}</h2>
          <p class="lead-soft">{T("partners.form_lead")}</p>
        </div>
        <div class="form-panel">
{form}
        </div>
      </div>
    </section>

{faq}"""
    return {"partners.html": page(
        root=root, active="partners", path="partners.html",
        jsonld=[breadcrumb_ld([("Home", ""), ("Partners", "partners.html")]), faq_ld],
        title="Partner With BCH Group | Hotels, Agents & Event Planners",
        description=texts.raw("partners.description"), body=body)}


HELP_FAQ = (1, 2, 3, 4, 5, 6, 7, 8)


def faq_pairs():
    """(question key, answer key) for every non-empty FAQ entry."""
    out = []
    for n in HELP_FAQ:
        q, a = f"home.faq_question_{n}", f"home.faq_answer_{n}"
        if n > 6:
            q, a = f"help.faq_question_{n}", f"help.faq_answer_{n}"
        if texts.raw(q).strip() and texts.raw(a).strip():
            out.append((q, a))
    return out


def build_help():
    root = ""
    pairs = faq_pairs()
    faq = "\n".join(f'        <details class="faq-item"><summary>{T(q)}</summary><p>{T(a)}</p></details>'
                    for q, a in pairs)
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": texts.raw(q),
         "acceptedAnswer": {"@type": "Answer", "text": texts.raw(a)}} for q, a in pairs]}
    wa = f"{WHATSAPP}?text={quote('Hi BCH Group, I need to change a booking.')}"
    hrefs = ["#faq", "#faq", "fleet.html#faq", "business.html#faq", "partners.html#faq", "#contact"]
    topics = "".join(f'<li><a href="{hrefs[i] if i < len(hrefs) else "#faq"}">{t}</a></li>'
                     for i, t in enumerate(T_lines("help.topics")))
    # The admin's "Taxi photo" slot (our own van) leads the Help page. The
    # default is a plain Irish road: the old stock van carried another firm's branding.
    van = SLOT_PHOTO.get("taxi") or local_photo("images/photo-commute.jpg")
    body = page_hero(root, [("Home", "index.html"), ("Help", None)],
                     T("help.title"), T("help.lead"), slot_photo=van, split=True,
                     extra=f'\n      <ul class="jump-links help-topics" aria-label="{T("help.topics_title")}">{topics}</ul>') + f"""

    <section class="section">
      <div class="wrap enquiry-grid help-grid" id="faq">
        <div>
          <h2>{T("help.faq_title")}</h2>
          <div class="faq-list">
{faq}
          </div>
        </div>
        <div class="form-panel" id="contact">
          <h2>{T("help.contact_title")}</h2>
          <p>{T("help.contact_text")}</p>
          <ul class="help-contact">
            <li><a class="btn btn-primary" href="tel:{E(PHONE)}">Call {E(PHONE_DISPLAY)}</a></li>
            <li><a class="btn btn-quiet" href="{E(WHATSAPP)}" target="_blank" rel="noopener">WhatsApp</a></li>
            <li><a class="btn btn-quiet" href="mailto:{E(EMAIL)}">{E(EMAIL)}</a></li>
          </ul>
          <h2 class="h-gap">{T("help.changes_title")}</h2>
          <p>{T("help.changes_text")}</p>
          <p class="help-contact"><a class="btn btn-quiet" href="{E(wa)}" target="_blank" rel="noopener">WhatsApp us about a booking</a></p>
        </div>
      </div>
    </section>"""
    return {"help.html": page(
        root=root, active="help", path="help.html",
        jsonld=[breadcrumb_ld([("Home", ""), ("Help", "help.html")]), faq_ld],
        title="Help Centre: Booking, Payment & Questions | BCH Group",
        description=texts.raw("help.description"), body=body)}


# ── index.html regions ───────────────────────────────────────────────────────

def replace_region(s, name, content):
    pat = re.compile(r"(<!-- @%s -->)(.*?)(\s*<!-- /@%s -->)" % (name, name), re.S)
    if not pat.search(s):
        raise BuildError([f"missing the @{name} marker"], "index.html template")
    return pat.sub(lambda m: m.group(1) + "\n" + content + m.group(3), s, count=1)


def sync_faq_jsonld(s):
    """Keep the FAQ structured data in step with edited FAQ questions/answers."""
    for key, default in texts.template_texts(s).items():
        if key.startswith(("home.faq_question_", "home.faq_answer_")) and texts.raw(key) != default:
            old = _json_inline(default)[1:-1]
            if old not in s:
                raise BuildError([f"FAQ structured data no longer contains {key}"],
                                 "index.html template")
            s = s.replace(old, _json_inline(texts.raw(key))[1:-1], 1)
    return s


def apply_index_photos(s):
    """Swap in uploaded hero / logo photos on index.html (no-op if unset).
    The taxi photo slot is used by the Help page header (build_help)."""
    hero, logo = (SLOT_PHOTO.get(k) for k in ("hero", "logo"))
    if hero:
        url = photo_url("hero", "", "")
        s = re.sub(r'<meta property="og:image" content="[^"]*">',
                   lambda m: f'<meta property="og:image" content="{url}">', s, count=1)
        s = re.sub(r'"image": "[^"]*"', lambda m: f'"image": "{url}"', s, count=1)
        s = s.replace('<link rel="preload" as="image" href="images/hero.jpg">',
                      f'<link rel="preload" as="image" href="{E(hero)}">')
        s = s.replace("</head>", f"  <style>.hero-bg{{background-image:url('{E(hero)}')}}</style>\n</head>", 1)
    if logo:
        url = photo_url("logo", "", "")
        s = s.replace('<link rel="apple-touch-icon" href="images/logo-500.png">',
                      f'<link rel="apple-touch-icon" href="{E(logo)}">')
        s = re.sub(r'"logo": "[^"]*"', lambda m: f'"logo": "{url}"', s, count=1)
    return s


# Homepage service bands and the photo each one uses: its own file first
# (drop images/band-<name>.jpg in to replace it), else a stand-in photo.
BANDS = {
    "airport": ("images/band-airport.jpg",),
    "intercity": ("images/band-intercity.jpg", "images/photo-intercity.jpg"),
    "events": ("images/band-events.jpg", "images/photo-events.jpg"),
}
KIND_LABEL = {"day": "Day tours", "pub": "Pub tours", "golf": "Golf trips"}


def band_image(band):
    """Photo for a homepage service band, or "" for a plain Ink panel (CSS),
    so a missing photo never breaks the page or the link check."""
    rel = next((r for r in BANDS[band] if local_photo(r)), None)
    if not rel:
        return ""
    return f'          <img class="band-img" src="{rel}" alt="" loading="lazy">'


def fare_data():
    """Fare table for the booking card's instant airport price (js/fares.js)."""
    data = _ld_dumps({
        "airport": [{"area": a, "to": to, "from": fr} for a, _, to, fr in AIRPORT_FARES],
        "long": [{"area": a, "price": p} for a, p in LONG_TRANSFERS],
    })
    return f'          <script id="fare-data" type="application/json">{data}</script>'


def tour_options():
    """Booking card: every published tour, grouped by kind, with its price."""
    groups = []
    for kind in KIND_ORDER:
        tours = published(kind)
        if not tours:
            continue
        opts = "".join(
            f'<option value="{E(t["name"])}" data-kind="{kind}" data-price="{price_attr(t)}" data-unit="{price_unit(t)}">{E(t["name"])}</option>'
            for t in tours)
        groups.append(f'                <optgroup label="{KIND_LABEL[kind]}">{opts}</optgroup>')
    return "\n".join(groups)


def vehicle_field():
    """Booking card: the vehicle choice (empty when no vehicle is published)."""
    vehicles = fleet_published()
    if not vehicles:
        return ""
    opts = "".join(
        f'<option value="{E(v["slug"])}" data-pax="{v["passengers"]}"'
        + (' data-fixed="1"' if v["slug"] == VAN_SLUG else "")
        + f'>{E(v["name"])} (up to {v["passengers"]})</option>' for v in vehicles)
    return f"""            <div class="field" id="cf-vehicle-field">
              <label for="cf-vehicle">{T("home.card_vehicle_label")}</label>
              <select id="cf-vehicle" name="vehicle"><option value="">Any suitable vehicle</option>{opts}</select>
            </div>
            <p class="card-hint" id="cf-vehicle-hint" aria-live="polite" hidden></p>"""


def from_price(v):
    """Lowest published tour price, only for the vehicle the fixed prices are for."""
    if v["slug"] != VAN_SLUG:
        return None
    prices = [t["price"] for t in published() if t["price"] is not None]
    return min(prices) if prices else None


_WHEELCHAIR_YES = re.compile(r"wheelchair", re.I)
_WHEELCHAIR_NO = re.compile(r"\b(not|no|non|without)\b", re.I)


def vehicle_spec_grid(v):
    """Spec sheet: passengers, suitcases, price and access (or a key feature)."""
    cells = [("Passengers", str(v["passengers"]))]
    if v["bags"]:
        cells.append(("Suitcases", str(v["bags"])))
    price = from_price(v)
    if price is not None:
        cells.append(("Price", "Tours from " + eur(price)))
    elif v["price_note"]:
        cells.append(("Price", E(v["price_note"])))
    feats = [f for f in v["features"] if isinstance(f, str) and f.strip()]
    if any(_WHEELCHAIR_YES.search(f) and not _WHEELCHAIR_NO.search(f) for f in feats):
        cells.append(("Access", "Ramp"))
    elif feats:
        cells.append(("Includes", E(feats[0])))
    return ('<dl class="spec-grid">' + "".join(
        f"<div><dt>{k}</dt><dd>{val}</dd></div>" for k, val in cells) + "</dl>")


def featured_slug(vehicles):
    slugs = [v["slug"] for v in vehicles]
    return VAN_SLUG if VAN_SLUG in slugs else slugs[0]


def fleet_showcase():
    """Homepage fleet: one featured vehicle with its spec sheet, tabs for the rest."""
    vehicles = fleet_published()
    if not vehicles:
        return ""
    featured = featured_slug(vehicles)
    items = []
    for v in vehicles:
        cls = "showcase-item is-featured" if v["slug"] == featured else "showcase-item"
        example = f'<p class="showcase-example">{E(v["example"])}</p>' if v["example"] else ""
        items.append(f"""        <article class="{cls}" id="sc-{E(v['slug'])}" data-vehicle="{E(v['slug'])}">
          <div class="showcase-media">{vehicle_media(v, "", "showcase-img")}</div>
          <div class="showcase-body">
            <h3>{E(v['name'])}</h3>
            {example}
            {vehicle_spec_grid(v)}
            <a class="btn btn-primary" href="index.html?vehicle={quote(v['slug'])}#booking">{T("fleet.book_button")}</a>
          </div>
        </article>""")
    tabs = ""
    if len(vehicles) > 1:
        buttons = "".join(
            f'<button type="button" role="tab" data-vehicle="{E(v["slug"])}" aria-controls="sc-{E(v["slug"])}"'
            f' aria-selected="{"true" if v["slug"] == featured else "false"}">'
            f'{E(v["name"])}<small>{v["passengers"]} seats'
            + (f' · {v["bags"]} bags' if v["bags"] else "") + "</small></button>"
            for v in vehicles)
        tabs = f'\n      <div class="showcase-tabs" role="tablist" aria-label="Vehicles" hidden>{buttons}</div>'
    return f"""  <section class="section fleet-strip" id="fleet-strip">
    <div class="wrap">
      <div class="section-head">
        <h2>{T("home.fleet_title")}</h2>
        <p>{T("home.fleet_intro")}</p>
      </div>
      <div class="showcase">
{chr(10).join(items)}
      </div>{tabs}
      <p class="tours-foot"><a class="link-strong" href="fleet.html">{T("home.fleet_link")}</a></p>
    </div>
  </section>"""


def teaser_row(cls, photo, title_key, text_key, button_key, href):
    img = local_photo(photo)
    media = (f'<img class="split-img" src="{img}" alt="" loading="lazy">' if img
             else '<div class="split-img split-panel" aria-hidden="true"></div>')
    return f"""      <article class="split {cls}">
        {media}
        <div class="split-body">
          <h2>{T(title_key)}</h2>
          <p>{T(text_key)}</p>
          <a class="btn btn-primary" href="{href}">{T(button_key)}</a>
        </div>
      </article>"""


def teasers():
    return f"""  <section class="section teasers" id="teasers">
    <div class="wrap splits">
{teaser_row("split-biz", "images/photo-business.jpg", "home.biz_title", "home.biz_text", "home.biz_button", "business.html")}
{teaser_row("split-partner", "images/band-tours.jpg", "home.partner_title", "home.partner_text", "home.partner_button", "partners.html")}
    </div>
  </section>"""


def build_index(out_dir):
    s = texts.dyn_template(TEMPLATE_INDEX.read_text())
    s = sync_faq_jsonld(s)
    s = replace_region(s, "nav", nav("", is_index=True, active="personal"))
    s = replace_region(s, "vehicle-field", vehicle_field())
    s = replace_region(s, "fleet-strip", fleet_showcase())
    s = replace_region(s, "teasers", teasers())
    s = replace_region(s, "faq-more", f'<a class="link-strong" href="help.html">{T("home.faq_all")}</a>')
    s = replace_region(s, "tours-grid", "\n".join(tour_card(t, "") for t in published()))
    s = replace_region(s, "fare-data", fare_data())
    s = replace_region(s, "tour-options", tour_options())
    for band in BANDS:
        s = replace_region(s, f"band-{band}", band_image(band))
    priced = [t["price"] for t in published("day") if t["price"] is not None]
    pattern = r"day tours from €\d+(?:,\d{3})*"
    if not re.search(pattern, s):
        raise BuildError(["meta description no longer mentions 'day tours from €…'"],
                         "index.html template")
    if priced:
        s = re.sub(pattern, "day tours from " + eur(min(priced)), s)
    s = apply_index_photos(s)
    if SITE_URL:
        base = SITE_URL.rstrip("/")
        s = s.replace('<meta property="og:image" content="images/hero.jpg">',
                      f'<meta property="og:image" content="{base}/images/hero.jpg">')
        s = re.sub(r'\n  <link rel="canonical"[^>]*>', '', s)
        s = s.replace('<meta name="robots"', f'<link rel="canonical" href="{base}/">\n  <meta name="robots"', 1)
        s = s.replace('"image": "images/hero.jpg"', f'"image": "{base}/images/hero.jpg"').replace('"logo": "images/logo.svg"', f'"logo": "{base}/images/logo.svg"')
    s = replace_region(s, "modal", "  " + MODAL)
    s = replace_region(s, "fab", "  " + FAB)
    s = replace_region(s, "footer", footer("", is_index=True))
    if 'css/pages.css' not in s:
        s = s.replace('<link rel="stylesheet" href="css/style.css">',
                      '<link rel="stylesheet" href="css/style.css">\n  <link rel="stylesheet" href="css/pages.css">')
    for rel in ("css/style.css", "css/pages.css"):
        s = s.replace(f'href="{rel}">', f'href="{asset(rel)}">')
    s = s.replace('<script src="js/main.js"></script>',
                  config_script("") + f'\n  <script src="{asset("js/fares.js")}"></script>'
                  f'\n  <script src="{asset("js/places.js")}"></script>'
                  f'\n  <script src="{asset("js/main.js")}"></script>')
    (out_dir / "index.html").write_text(texts.replace_markers(s))


# ── Link check ───────────────────────────────────────────────────────────────

def check_links(out_dir, files):
    out_dir = Path(out_dir)
    bad = []
    for rel in files:
        path = out_dir / rel
        text = path.read_text()
        for ref in re.findall(r'(?:href|src)="([^"]+)"', text) + re.findall(r"url\('([^']+)'\)", text):
            if re.match(r"^(https?:|mailto:|tel:|data:|#|javascript:)", ref):
                continue
            target = (path.parent / ref.split("#")[0].split("?")[0]).resolve()
            if not target.exists():
                bad.append(f"{rel}: {ref}")
    css = out_dir / "css" / "style.css"
    for ref in re.findall(r"url\('([^']+)'\)", css.read_text()):
        if not (css.parent / ref).resolve().exists():
            bad.append(f"css/style.css: {ref}")
    return bad


def build_site(content, out_dir, extra_files=None):
    """Render the site for `content` into `out_dir` (emptied first).

    `extra_files` maps relative paths (e.g. "uploads/abc.jpg") to bytes; they
    are written after out_dir is emptied and before the link check.
    """
    out_dir = Path(out_dir).resolve()
    in_repo = out_dir == ROOT_DIR or ROOT_DIR in out_dir.parents
    in_dist = out_dir == ROOT_DIR / "dist" or (ROOT_DIR / "dist") in out_dir.parents
    if out_dir in ROOT_DIR.parents or out_dir == Path(out_dir.anchor) or (in_repo and not in_dist):
        raise ValueError(f"refusing to build into {out_dir}")
    _configure(content)
    if out_dir.exists():
        for child in out_dir.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    for d in ("css", "js", "images"):
        shutil.copytree(ROOT_DIR / d, out_dir / d)
    for rel, data in (extra_files or {}).items():
        target = (out_dir / rel).resolve()
        if out_dir not in target.parents:
            raise ValueError(f"extra file outside out_dir: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    pages = {}
    for builder in (build_tour_pages, build_tours_hub, build_pub_tours, build_golf_trips, build_multi_day, build_calculator, build_destinations, build_blog,
                    build_fleet, build_business, build_partners, build_help):
        pages.update(builder())
    for rel, text in pages.items():
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    build_index(out_dir)
    (out_dir / "js" / "config.js").write_text(CONFIG_JS)
    # Contact tokens live in the template, partials and blog posts; fill them
    # in every generated page in one place.
    for rel in ["index.html"] + list(pages):
        path = out_dir / rel
        path.write_text(fill_tokens(path.read_text()))

    if SITE_URL:
        hidden = {f"tours/{t['slug']}.html" for t in TOURS if not t["published"]}
        urls = [""] + sorted(u for u in pages if u not in hidden)
        base = SITE_URL.rstrip("/")
        xml = "\n".join(f"  <url><loc>{base}/{u}</loc></url>" for u in urls)
        (out_dir / "sitemap.xml").write_text(
            f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{xml}\n</urlset>\n')
        (out_dir / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")

    leftover = sorted({m.group(0)
                       for p in out_dir.rglob("*") if p.suffix in (".html", ".js")
                       for m in _TOKEN_RE.finditer(p.read_text())})
    if leftover:
        raise BuildError([f"Unknown placeholder {tok} in page text" for tok in leftover[:3]]
                         + ([f"and {len(leftover) - 3} more"] if len(leftover) > 3 else []),
                         "Unfilled {{tokens}}")
    bad = check_links(out_dir, ["index.html"] + list(pages))
    if bad:
        raise BuildError(bad)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Build the BCH Group site.")
    ap.add_argument("--out", default=str(ROOT_DIR / "dist"), help="output directory (default: dist/)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    try:
        build_site(merge(default_content(), {}), out)
    except BuildError as e:
        print(f"Build failed ({e.args[0].split(':')[0]}):")
        for b in e.broken:
            print("  " + b)
        sys.exit(1)
    print(f"Built {len(list(out.rglob('*.html')))} HTML files in {out}")
    print("All local links OK")


if __name__ == "__main__":
    main()
