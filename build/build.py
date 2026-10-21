#!/usr/bin/env python3
"""Generate the BCH Taxi site from build/data.py and build/posts.py.

Usage:  python3 build/build.py [--out DIR]     (default DIR: dist/)

build_site(content, out_dir) renders the whole site into out_dir:
- index.html from build/templates/index.html (marked regions filled in)
- tours.html, tours/*.html, multi-day-tours.html, price-calculator.html,
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
                     price_unit, resolve_redirect)
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
    return _BRACE_RE.sub(lambda m: "\\u007b", json.dumps(obj, ensure_ascii=False, **kw))


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


class BuildError(Exception):
    def __init__(self, broken, message="Broken links"):
        self.broken = list(broken)
        super().__init__(message + ": " + "; ".join(self.broken))


KIND_ORDER = ("day", "pub", "golf")
# Page that lists each kind, with its breadcrumb name and nav key.
KIND_PAGE = {
    "day": ("tours.html", "Tours", "tours"),
    "pub": ("pub-tours.html", "Pub Tours", "pub"),
    "golf": ("golf-trips.html", "Golf Trips", "golf"),
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
    st = content["settings"]
    texts.configure(content.get("texts"))
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
                  if pid in paths}
    TOUR_PHOTO = {t["slug"]: paths[t["photo"]] for t in TOURS if t.get("photo") in paths}
    MODAL = fill_tokens(_MODAL_RAW)
    FAB = fill_tokens(_FAB_RAW)
    CONFIG_JS = ("window.BCH = " + _json_inline({
        "email": EMAIL, "waNumber": st["whatsapp_number"],
        "phoneDisplay": PHONE_DISPLAY}) + ";\n")
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


def eur(n):
    return f"€{n:,}"


def multi_price(m):
    return m["days"] * MULTI_DAY_RATE


def idx(root, anchor, is_index):
    """Link to a section of the home page."""
    return f"#{anchor}" if is_index else f"{root}index.html#{anchor}"


# ── Shared chrome ────────────────────────────────────────────────────────────

BRAND = ('<span class="brand-mark" aria-hidden="true">BCH</span>'
         '<span class="brand-word">BCH Taxi<small>Taxi · Airport · Tours</small></span>')


def nav(root, is_index=False, active=""):
    items = [
        ("Tours", f"{root}tours.html", "tours"),
        ("Pub Tours", f"{root}pub-tours.html", "pub"),
        ("Golf", f"{root}golf-trips.html", "golf"),
        ("Multi-Day", f"{root}multi-day-tours.html", "multi"),
        ("Prices", f"{root}price-calculator.html", "prices"),
        ("Airport", idx(root, "airport", is_index), "airport"),
        ("Business", idx(root, "corporate", is_index), "business"),
        ("Blog", f"{root}blog.html", "blog"),
        ("Contact", idx(root, "contact", is_index), "contact"),
    ]
    current = ' aria-current="page"'
    lis = "\n".join(
        f'      <li><a href="{href}"{current if key == active else ""}>{label}</a></li>'
        for label, href, key in items)
    home = "#" if is_index else f"{root}index.html"
    return f"""  <nav>
    <a href="{home}" class="brand" aria-label="BCH Taxi home">
      {BRAND}
    </a>
    <ul class="nav-links">
{lis}
      <li class="nav-call"><a href="tel:{E(PHONE)}">Call {E(PHONE_DISPLAY)}</a></li>
      <li><a href="{idx(root, 'booking', is_index)}" class="nav-cta">Book Taxi</a></li>
    </ul>
    <div class="mobile-toggle" onclick="document.querySelector('.nav-links').classList.toggle('open')">
      <span></span><span></span><span></span>
    </div>
  </nav>"""


def footer(root, is_index=False):
    favs = [t for t in published() if t["fav"]]
    popular = (favs + [t for t in published("day") if t not in favs])[:6]
    tour_links = "\n".join(f'          <li><a href="{root}tours/{t["slug"]}.html">{E(t["name"])}</a></li>' for t in popular)
    return f"""  <footer class="site-footer">
    <div class="footer-grid">
      <div class="footer-about">
        <a href="{'#' if is_index else root + 'index.html'}" class="brand" aria-label="BCH Taxi home">
          {BRAND}
        </a>
        <p>{T("footer.about")}</p>
        <ul class="footer-contact">
          <li><a href="tel:{E(PHONE)}"><span>Call</span>{E(PHONE_DISPLAY)}</a></li>
          <li><a href="{E(WHATSAPP)}" target="_blank" rel="noopener"><span>WhatsApp</span>Message us</a></li>
          <li><a href="mailto:{E(EMAIL)}"><span>Email</span>{E(EMAIL)}</a></li>
        </ul>
      </div>
      <div>
        <h4>Explore</h4>
        <ul>
          <li><a href="{'#' if is_index else root + 'index.html'}">Home</a></li>
          <li><a href="{root}tours.html">Day Tours</a></li>
          <li><a href="{root}pub-tours.html">Pub Tours</a></li>
          <li><a href="{root}golf-trips.html">Golf Trips</a></li>
          <li><a href="{root}multi-day-tours.html">Multi-Day Tours</a></li>
          <li><a href="{root}destinations.html">Destinations</a></li>
          <li><a href="{root}blog.html">Blog &amp; Travel Guides</a></li>
          <li><a href="{idx(root, 'faq', is_index)}">FAQ</a></li>
        </ul>
      </div>
      <div>
        <h4>Services</h4>
        <ul>
          <li><a href="{idx(root, 'services', is_index)}">Local Taxi</a></li>
          <li><a href="{idx(root, 'airport', is_index)}">Airport Transfers</a></li>
          <li><a href="{idx(root, 'corporate', is_index)}">Corporate &amp; Business</a></li>
          <li><a href="{idx(root, 'school', is_index)}">School Transport</a></li>
          <li><a href="{root}price-calculator.html">Price Calculator</a></li>
        </ul>
      </div>
      <div>
        <h4>Popular Tours</h4>
        <ul>
{tour_links}
        </ul>
      </div>
      <div class="footer-cta">
        <h4>{T("footer.plan_title")}</h4>
        <p>{T("footer.plan_text")}</p>
        <a href="{idx(root, 'booking', is_index)}" class="btn btn-gold">Book a Taxi</a>
        <a href="{root}price-calculator.html" class="btn btn-outline">Get a Quote</a>
      </div>
    </div>
    <div class="footer-bottom">
      <p>&copy; 2026 BCH Taxi. All rights reserved.</p>
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
  <meta name="theme-color" content="#062a1f">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="BCH Taxi">
  <meta property="og:locale" content="en_IE">
  <meta property="og:title" content="{E(title)}">
  <meta property="og:description" content="{E(description)}">
  <meta property="og:image" content="{photo_url('hero', root, 'images/hero.jpg')}">
  <meta name="twitter:card" content="summary_large_image">{canonical}
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%230a0a0a'/%3E%3Ctext x='32' y='42' font-family='Georgia,serif' font-size='26' font-weight='700' fill='%23c9a84c' text-anchor='middle'%3EBCH%3C/text%3E%3C/svg%3E">
  <link rel="apple-touch-icon" href="{photo_url('logo', root, 'images/logo.svg', absolute=False)}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=Outfit:wght@300;400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{root}css/style.css">
  <link rel="stylesheet" href="{root}css/pages.css">{ld}
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
  <script src="{root}js/main.js"></script>{extra_js}
</body>
</html>
"""


def page_hero(root, crumbs, label, h1, lead, extra=""):
    trail = " <span>/</span> ".join(
        f'<a href="{href}">{E(name)}</a>' if href else f'<span aria-current="page">{E(name)}</span>'
        for name, href in crumbs)
    return f"""    <section class="page-hero">
      <nav class="crumbs" aria-label="Breadcrumb">{trail}</nav>
      <span class="hero-label">{label}</span>
      <h1>{h1}</h1>
      <p class="page-lead">{lead}</p>{extra}
    </section>"""


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
    return f"<small>From</small>{price_label(t)}<span>{price_unit(t)}{' · ' + note if note else ''}</span>"


def tour_card(t, root, detail_link=True):
    li = "".join(f"<li>{E(x)}</li>" for x in t["highlights"][:4])
    extra = t["highlights"][4:]
    more = (f'<details class="tour-more"><summary>+{len(extra)} more</summary><ul class="tour-list">'
            + "".join(f"<li>{E(x)}</li>" for x in extra) + "</ul></details>") if extra else ""
    badge = '<span class="tour-badge">Most Popular</span>' if t["fav"] else ""
    photo = tour_photo(t, root) + "\n        " if t["slug"] in TOUR_PHOTO else ""
    details = f'<a class="tour-details" href="{root}tours/{t["slug"]}.html">View tour details →</a>' if detail_link else ""
    return f"""      <article class="tour-card reveal{' fav' if t['fav'] else ''}">
        {photo}{badge}
        <span class="tour-region">{E(t['region'])}</span>
        <h3><a href="{root}tours/{t['slug']}.html">{E(t['name'])}</a></h3>
        <div class="tour-chips"><span>{E(t['duration'])}</span><span>Private</span><span>Up to 8</span></div>
        <p>{E(t['desc'])}</p>
        <ul class="tour-list">{li}</ul>
        {more}
        {details}
        <div class="tour-foot">
          <div class="tour-price">{price_html(t)}</div>
          <button type="button" class="btn btn-gold tour-book" data-price="{price_attr(t)}" data-unit="{price_unit(t)}" data-tour="{E(t['name'])}">Book</button>
        </div>
      </article>"""


def multi_card(m, root):
    days = "".join(f"<li><strong>Day {i}</strong>{E(d)}</li>" for i, d in enumerate(m["plan"], 1))
    return f"""      <article class="multi-card reveal" id="{m['slug']}">
        <div class="multi-head">
          <span class="tour-region">{m['days']} days · sample route</span>
          <h3>{E(m['name'])}</h3>
          <p>{E(m['summary'])}</p>
        </div>
        <ol class="multi-days">{days}</ol>
        <div class="tour-foot">
          <div class="tour-price"><small>From</small>{eur(multi_price(m))}<span>{m['days']} days × {eur(MULTI_DAY_RATE)} per vehicle</span></div>
          <button type="button" class="btn btn-gold tour-book" data-price="{multi_price(m)}" data-tour="{E(m['name'])} ({m['days']}-day tour)">Book</button>
        </div>
      </article>"""


def cta_band(root, title_key="cta.title", text_key="cta.text"):
    return f"""    <section class="cta-band theme-dark">
      <div class="reveal">
        <h2>{T(title_key)}</h2>
        <p>{T(text_key)}</p>
      </div>
      <div class="cta-actions reveal">
        <a href="{root}index.html#booking" class="btn btn-gold">Book a Taxi</a>
        <a href="{E(WHATSAPP)}" class="btn btn-whatsapp" target="_blank" rel="noopener">WhatsApp Us</a>
        <a href="tel:{E(PHONE)}" class="btn btn-outline">Call {E(PHONE_DISPLAY)}</a>
      </div>
    </section>"""


def group_band(root, is_index=False):
    """Banner for groups bigger than one van."""
    book = (f'<button type="button" class="btn btn-gold" data-service="Group transport (9+)">Get a Group Quote</button>'
            if is_index else
            f'<a href="{root}index.html?service=Group%20transport%20(9%2B)#booking" class="btn btn-gold">Get a Group Quote</a>')
    points = "\n".join(f"          <li>{x}</li>" for x in T_lines("group.points"))
    return f"""  <section class="group-band theme-teal">
    <div class="group-inner reveal">
      <div class="group-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/></svg>
      </div>
      <div class="group-text">
        <span class="section-label">{T("group.label")}</span>
        <h2>More than {MAX_PASSENGERS} {T("group.title_rest")}</h2>
        <p>{T("group.text")}</p>
        <ul class="group-points">
{points}
        </ul>
      </div>
      <div class="group-actions">
        {book}
        <a href="{E(WHATSAPP)}?text={quote("Hi BCH Taxi, I'd like a quote for a group of more than 8 people.")}" class="btn btn-whatsapp" target="_blank" rel="noopener">Ask on WhatsApp</a>
      </div>
    </div>
  </section>"""


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
        calc_link = (f'\n          <a class="book-alt" href="{root}price-calculator.html?tour={t["slug"]}">Add extras in the price calculator →</a>'
                     if kind == "day" and t["price"] is not None else "")
        also = "\n".join(tour_card(o, root) for o in others[:3])
        more = f"""
    <section class="theme-mint">
      <div class="reveal">
        <span class="section-label">{T("tour.more_label")}</span>
        <h2 class="section-title">{T("tour.more_title")}</h2>
      </div>
      <div class="tours-grid">
{also}
      </div>
    </section>
""" if also else ""
        body = page_hero(root, [(n, (root + h) if h else None) for n, h in crumbs], E(t["region"]),
                         E(t["name"]) + " " + suffix,
                         E(t["desc"]),
                         f"""
      <div class="hero-meta">
        <span>{E(t['duration'])}</span><span>{"Private tour" if kind == "day" else KINDS[kind]}</span><span>Up to 8 passengers</span><span>From Dublin: {E(t['drive'])}</span>
      </div>""") + f"""

    <section class="theme-light tour-detail">
      <div class="detail-grid">
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
        <aside class="book-card">
          <span class="tour-region">{KINDS[kind] if kind != "day" else "Private tour"}</span>
          <div class="tour-price">{price_html(t, "up to 8 people")}</div>
          <ul class="book-facts">
            <li><span>Duration</span>{E(t['duration'])}</li>
            <li><span>Drive from Dublin</span>{E(t['drive'])}</li>
            <li><span>Pickup</span>Dublin or Meath</li>
          </ul>
          <button type="button" class="btn btn-gold tour-book" data-price="{price_attr(t)}" data-unit="{unit}" data-tour="{E(t['name'])}">Book This Tour</button>
          <a class="btn btn-whatsapp" href="{E(WHATSAPP)}?text={quote(f"Hi BCH Taxi, I'd like to ask about the {t['name']} tour.")}" target="_blank" rel="noopener">Ask on WhatsApp</a>{calc_link}
          <p class="book-group">More than 8 people? <a href="{root}index.html?service=Group%20transport%20(9%2B)#booking">We can arrange extra vehicles.</a></p>
        </aside>
      </div>
    </section>
{more}
{group_band(root)}

{cta_band(root)}"""
        tour_ld = {
            "@context": "https://schema.org", "@type": "TouristTrip",
            "name": f"{t['name']} {suffix}", "description": t["desc"],
            "touristType": "Private group",
            "itinerary": {"@type": "ItemList", "itemListElement": [
                {"@type": "ListItem", "position": i, "name": h} for i, h in enumerate(t["highlights"], 1)]},
            "provider": {"@type": "TaxiService", "name": "BCH Taxi", "telephone": PHONE},
        }
        if t["price"] is not None:
            tour_ld["offers"] = {"@type": "Offer", "price": t["price"], "priceCurrency": "EUR",
                                 "description": f"{unit.capitalize()}, up to 8 passengers"}
        ld = [tour_ld, breadcrumb_ld([("Home", ""), (list_name, listing), (t["name"], f"tours/{t['slug']}.html")])]
        unit_title = "per " + unit[4:].capitalize()
        origin = " from Dublin" if kind == "day" else ""
        title = f"{t['name']} {suffix}{origin}"
        if t["price"] is not None:
            title += f" | {price_label(t)} {unit_title}"
        title += " | BCH Taxi"
        if kind == "day":
            desc = f"Private {t['name']} day tour from Dublin or Meath in a wheelchair-accessible 8-seater. {t['duration']}"
        else:
            desc = f"Private {t['name']} {KIND_NOUN[kind]} in a wheelchair-accessible 8-seater. {t['duration']}"
        desc += (f", from {price_label(t)} {unit} for up to 8 people." if t["price"] is not None
                 else ", for up to 8 people.")
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
    body = page_hero(root, [("Home", "index.html"), (list_name, None)], T(kind + ".label"),
                     T(kind + ".title"), T(kind + ".lead")) + f"""

    <section class="theme-mint">
      <div class="tours-grid">
{cards}
      </div>
    </section>

    <section class="theme-light">
      <div class="note-box reveal">
        <h3>{T("tour.included_title")}</h3>
        <ul class="check-list">{inc}</ul>
      </div>
    </section>

{cta_band(root, kind + ".cta_title", kind + ".cta_text")}"""
    return {listing: page(
        root=root, active=active, path=listing,
        jsonld=[breadcrumb_ld([("Home", ""), (list_name, listing)])],
        title=title, description=texts.raw(kind + ".description"), body=body)}


def build_pub_tours():
    return build_kind_listing("pub", "Rural Pub Tours from Dublin & Meath | BCH Taxi")


def build_golf_trips():
    return build_kind_listing("golf", "Golf Trips from Dublin & Meath | BCH Taxi")


def build_tours_hub():
    root = ""
    crumbs = [("Home", "index.html"), ("Tours", None)]
    day = published("day")
    n = len(day)
    lead_count = f"{count_word(n)} full-day private tours" if n else "Full-day private tours"
    body = page_hero(root, crumbs, T("tours.label"), T("tours.title"),
                     f"{lead_count} {T('tours.lead')}") + f"""

    <section class="theme-mint">
      <div class="tours-grid">
{chr(10).join(tour_card(t, root) for t in day)}
      </div>
    </section>

    <section class="theme-light">
      <div class="split-promo reveal">
        <div>
          <span class="section-label">{T("tours.longer_label")}</span>
          <h2 class="section-title">{T("tours.multi_title")}</h2>
          <p class="section-desc">{T("tours.multi_before")} {eur(MULTI_DAY_RATE)} {T("tours.multi_after")}</p>
        </div>
        <div class="promo-actions">
          <a href="multi-day-tours.html" class="btn btn-gold">See Multi-Day Tours</a>
          <a href="destinations.html" class="btn btn-outline-dark">Destination Guide</a>
        </div>
      </div>
    </section>

{group_band(root)}

{cta_band(root)}"""
    return {"tours.html": page(
        root=root, active="tours", path="tours.html", jsonld=[breadcrumb_ld([("Home", ""), ("Tours", "tours.html")])],
        title="Private Day Tours of Ireland from Dublin | BCH Taxi",
        description=(f"{n} private day tours from Dublin and Meath: " if n else "Private day tours from Dublin and Meath: ")
        + (", ".join(sample_names(day)) + " and more. " if n else "")
        + "Per-vehicle prices for up to 8 people.",
        body=body)}


def build_multi_day():
    root = ""
    crumbs = [("Home", "index.html"), ("Multi-Day Tours", None)]
    notes = "".join(f"\n          <li>{x}</li>" for x in T_lines("multi.notes"))
    body = page_hero(root, crumbs, T("multi.label"), T("multi.title"),
                     f"{T('multi.lead_before')} {eur(MULTI_DAY_RATE)} {T('multi.lead_after')}") + f"""

    <section class="theme-mint">
      <div class="multi-grid">
{chr(10).join(multi_card(m, root) for m in MULTI_DAY)}
      </div>
      <div class="note-box reveal">
        <h3>{T("multi.notes_title")}</h3>
        <ul class="check-list">
          <li>{eur(MULTI_DAY_RATE)} {T("multi.note_rate")}</li>{notes}
        </ul>
        <a href="price-calculator.html" class="btn btn-gold">Price a Custom Trip</a>
      </div>
    </section>

{cta_band(root, "multi.cta_title", "multi.cta_text")}"""
    return {"multi-day-tours.html": page(
        root=root, active="multi", path="multi-day-tours.html",
        jsonld=[breadcrumb_ld([("Home", ""), ("Multi-Day Tours", "multi-day-tours.html")])],
        title="Multi-Day Private Tours of Ireland | BCH Taxi",
        description=f"Private multi-day tours of Ireland with your own driver, from {eur(MULTI_DAY_RATE)} per day for up to 8 people. Sample routes: West Coast, Kerry, Causeway Coast and the Wild Atlantic Way.",
        body=body)}


def build_calculator():
    root = ""
    crumbs = [("Home", "index.html"), ("Price Calculator", None)]
    calc_tours = [t for t in published("day") if t["price"] is not None]
    data = {
        "tours": [{"slug": t["slug"], "name": t["name"], "price": t["price"]} for t in calc_tours],
        "multi": [{"slug": m["slug"], "name": m["name"], "days": m["days"]} for m in MULTI_DAY],
        "dayRate": MULTI_DAY_RATE, "hourRate": EXTRA_HOUR_RATE, "maxPax": MAX_PASSENGERS,
        "airport": [{"area": a, "to": to, "from": fr} for a, _, to, fr in AIRPORT_FARES]
                   + [{"area": a, "to": p, "from": p} for a, p in LONG_TRANSFERS],
    }
    tour_opts = "".join(f'<option value="{t["slug"]}">{E(t["name"])} · {eur(t["price"])}</option>' for t in calc_tours)
    multi_opts = "".join(f'<option value="{m["slug"]}">{E(m["name"])} · {m["days"]} days</option>' for m in MULTI_DAY)
    air_opts = "".join(f'<option value="{i}">{E(a["area"])}</option>' for i, a in enumerate(data["airport"]))
    dial = re.search(r'<select name="dial".*?</select>', MODAL, re.S).group(0)
    body = page_hero(root, crumbs, T("calc.label"), T("calc.title"), T("calc.lead")) + f"""

    <section class="theme-light calc-section">
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
            <div class="form-field"><label for="calc-name">Full Name *</label><input id="calc-name" name="name" type="text" autocomplete="name" required data-label="Name"></div>
            <div class="form-field"><label for="calc-email">Email *</label><input id="calc-email" name="email" type="email" autocomplete="email" required data-label="Email"></div>
            <div class="form-field"><label for="calc-phone">Phone *</label><div class="phone-row">{dial}<input id="calc-phone" name="phone" type="tel" autocomplete="tel-national" required data-label="Phone"></div></div>
            <div class="form-field"><label for="calc-date">Travel date</label><input id="calc-date" name="date" type="date" data-label="Travel date"></div>
            <div class="form-field"><label for="calc-notes">Notes</label><textarea id="calc-notes" name="notes" rows="3" placeholder="Pickup area, special requests…" data-label="Notes"></textarea></div>
            <input class="form-honey" type="text" name="_honey" tabindex="-1" autocomplete="off" aria-hidden="true">
            <button type="submit" class="btn btn-gold btn-wide" id="calc-send"><span class="send-label">Request Fixed Quote</span></button>
            <button type="button" class="btn btn-whatsapp btn-wide" id="calc-wa">Send on WhatsApp</button>
            <p class="form-status" id="calc-status" role="status" aria-live="polite"></p>
            <p class="form-legal">{T("calc.legal")}</p>
          </div>
        </aside>
      </form>
      <script id="calc-data" type="application/json">{_ld_dumps(data)}</script>
    </section>

    <section class="theme-mint">
      <div class="reveal">
        <span class="section-label">{T("calc.how_label")}</span>
        <h2 class="section-title">{T("calc.how_title")}</h2>
      </div>
      <div class="steps-grid">
        <div class="step-card reveal"><span class="calc-num">1</span><h3>{T("calc.step1_title")}</h3><p>{T("calc.step1_text")}</p></div>
        <div class="step-card reveal"><span class="calc-num">2</span><h3>{T("calc.step2_title")}</h3><p>{T("calc.step2_text")}</p></div>
        <div class="step-card reveal"><span class="calc-num">3</span><h3>{T("calc.step3_title")}</h3><p>{T("calc.step3_text")}</p></div>
        <div class="step-card reveal"><span class="calc-num">4</span><h3>{T("calc.step4_title")}</h3><p>{T("calc.step4_text")}</p></div>
      </div>
    </section>"""
    return {"price-calculator.html": page(
        root=root, active="prices", path="price-calculator.html",
        jsonld=[breadcrumb_ld([("Home", ""), ("Price Calculator", "price-calculator.html")])],
        title="Tour & Taxi Price Calculator | Instant Quote | BCH Taxi",
        description="Work out the price of your Ireland day tour, multi-day trip or Dublin Airport transfer instantly. Per-vehicle prices for up to 8 passengers.",
        body=body, extra_js=f'\n  <script src="{root}js/calculator.js"></script>')}


def build_destinations():
    root = ""
    crumbs = [("Home", "index.html"), ("Destinations", None)]
    groups = []
    for area in AREAS:
        items = [t for t in published("day") if t["area"] == area]
        if not items:
            continue
        cards = "\n".join(f"""        <a class="dest-card reveal" href="tours/{t['slug']}.html">
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
    body = page_hero(root, crumbs, T("dest.label"), T("dest.title"), T("dest.lead")) + f"""

    <section class="theme-light">
{chr(10).join(groups)}
      <p class="tours-note">{T("dest.note_before")} <a href="index.html#booking">Ask us</a>{T("dest.note_after")}</p>
    </section>

{cta_band(root)}"""
    return {"destinations.html": page(
        root=root, active="tours", path="destinations.html",
        jsonld=[breadcrumb_ld([("Home", ""), ("Destinations", "destinations.html")])],
        title="Ireland Destination Guide: Day Trips & Driving Times from Dublin | BCH Taxi",
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
    return re.sub(r"tours/([a-z0-9-]+)\.html", fix, body).replace("{ROOT}", root)


def build_blog():
    out = {}
    root = ""
    cards = "\n".join(f"""        <a class="post-card reveal" href="blog/{p['slug']}.html">
          <span class="tour-region">{E(p['topic'])}</span>
          <h3>{E(p['title'])}</h3>
          <p>{E(p['summary'])}</p>
          <span class="post-meta">{fmt_date(p['date'])} · Read article →</span>
        </a>""" for p in POSTS)
    body = page_hero(root, [("Home", "index.html"), ("Blog", None)], T("blog.label"), T("blog.title"), T("blog.lead")) + f"""

    <section class="theme-light">
      <div class="post-grid">
{cards}
      </div>
    </section>

{cta_band(root)}"""
    out["blog.html"] = page(root=root, active="blog", path="blog.html",
                            jsonld=[breadcrumb_ld([("Home", ""), ("Blog", "blog.html")])],
                            title="Ireland Travel Guides & Taxi Tips | BCH Taxi Blog",
                            description="Practical guides to day trips from Dublin, Dublin Airport transfers, accessible travel and planning a road trip around Ireland.",
                            body=body)

    for p in POSTS:
        root = "../"
        others = [o for o in POSTS if o["slug"] != p["slug"]][:3]
        more = "\n".join(f"""        <a class="post-card reveal" href="{o['slug']}.html">
          <span class="tour-region">{E(o['topic'])}</span>
          <h3>{E(o['title'])}</h3>
          <p>{E(o['summary'])}</p>
        </a>""" for o in others)
        body = page_hero(root, [("Home", root + "index.html"), ("Blog", root + "blog.html"), (p["title"], None)],
                         E(p["topic"]), E(p["title"]), E(p["summary"]),
                         f'\n      <div class="hero-meta"><span>{fmt_date(p["date"])}</span><span>BCH Taxi</span></div>') + f"""

    <section class="theme-light">
      <article class="post-body">
{post_body(p['body'], root)}
      </article>
    </section>

    <section class="theme-mint">
      <div class="reveal"><span class="section-label">Keep reading</span><h2 class="section-title">More travel guides</h2></div>
      <div class="post-grid">
{more}
      </div>
    </section>

{cta_band(root)}"""
        ld = [{
            "@context": "https://schema.org", "@type": "BlogPosting",
            "headline": p["title"], "description": p["summary"], "datePublished": p["date"],
            "author": {"@type": "Organization", "name": "BCH Taxi"},
            "publisher": {"@type": "Organization", "name": "BCH Taxi"},
        }, breadcrumb_ld([("Home", ""), ("Blog", "blog.html"), (p["title"], f"blog/{p['slug']}.html")])]
        out[f"blog/{p['slug']}.html"] = page(root=root, active="blog", path=f"blog/{p['slug']}.html", jsonld=ld,
                                             title=f"{p['title']} | BCH Taxi", description=p["summary"], body=body)
    return out


# ── index.html regions ───────────────────────────────────────────────────────

def replace_region(s, name, content):
    pat = re.compile(r"(<!-- @%s -->)(.*?)(\s*<!-- /@%s -->)" % (name, name), re.S)
    if not pat.search(s):
        raise BuildError([f"missing the @{name} marker"], "index.html template")
    return pat.sub(lambda m: m.group(1) + "\n" + content + m.group(3), s, count=1)


def replace_inline(s, name, value):
    """Replace a value wrapped in inline markers: <!-- @name -->value<!-- /@name -->."""
    pat = re.compile(r"(<!-- @%s -->).*?(<!-- /@%s -->)" % (name, name), re.S)
    if not pat.search(s):
        raise BuildError([f"missing the @{name} marker"], "index.html template")
    return pat.sub(lambda m: m.group(1) + value + m.group(2), s)


def sync_faq_jsonld(s):
    """Keep the FAQ structured data in step with edited FAQ questions/answers."""
    for key, default in texts.template_texts(s).items():
        if key.startswith("home.faq_") and texts.raw(key) != default:
            old = _json_inline(default)[1:-1]
            if old not in s:
                raise BuildError([f"FAQ structured data no longer contains {key}"],
                                 "index.html template")
            s = s.replace(old, _json_inline(texts.raw(key))[1:-1], 1)
    return s


def apply_index_photos(s):
    """Swap in uploaded hero / taxi / logo photos on index.html (no-op if unset)."""
    hero, taxi, logo = (SLOT_PHOTO.get(k) for k in ("hero", "taxi", "logo"))
    if hero:
        url = photo_url("hero", "", "")
        s = re.sub(r'<meta property="og:image" content="[^"]*">',
                   lambda m: f'<meta property="og:image" content="{url}">', s, count=1)
        s = re.sub(r'"image": "[^"]*"', lambda m: f'"image": "{url}"', s, count=1)
        s = s.replace('<link rel="preload" as="image" href="images/hero.jpg">',
                      f'<link rel="preload" as="image" href="{E(hero)}">')
        s = s.replace("</head>", f"  <style>.hero-bg{{background-image:url('{E(hero)}')}}</style>\n</head>", 1)
    if taxi:
        s = re.sub(r'<img src="images/taxi\.jpg"([^>]*?) width="899" height="658">',
                   lambda m: f'<img src="{E(taxi)}"{m.group(1)}>', s, count=1)
    if logo:
        url = photo_url("logo", "", "")
        s = s.replace('<link rel="apple-touch-icon" href="images/logo.svg">',
                      f'<link rel="apple-touch-icon" href="{E(logo)}">')
        s = re.sub(r'"logo": "[^"]*"', lambda m: f'"logo": "{url}"', s, count=1)
    return s


def build_index(out_dir):
    s = TEMPLATE_INDEX.read_text()
    fares = "\n".join(
        f'        <div class="fare-row"><span class="fare-place">{E(a)}</span><span class="fare-km">{km}</span>'
        f'<span class="fare-price"><small>To airport</small>{eur(to)}</span><span class="fare-price"><small>From airport</small>{eur(fr)}</span></div>'
        for a, km, to, fr in AIRPORT_FARES)
    s = sync_faq_jsonld(s)
    s = replace_region(s, "nav", nav("", is_index=True))
    s = replace_region(s, "tours-grid", "\n".join(tour_card(t, "") for t in published()))
    s = replace_region(s, "fares", fares)
    s = replace_region(s, "group-band", group_band("", is_index=True))
    s = replace_region(s, "fare-long", "\n".join(
        f'      <div class="fare-long-card"><span>Dublin Airport ⇄ {E(a)}</span><strong>{eur(p)}</strong></div>'
        for a, p in LONG_TRANSFERS))
    s = replace_inline(s, "min-fare", eur(min(to for _, _, to, _ in AIRPORT_FARES)) + "+")
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
    s = s.replace('<script src="js/main.js"></script>',
                  config_script("") + '\n  <script src="js/main.js"></script>')
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


def build_site(content, out_dir):
    """Render the site for `content` into `out_dir` (emptied first)."""
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

    pages = {}
    for builder in (build_tour_pages, build_tours_hub, build_pub_tours, build_golf_trips, build_multi_day, build_calculator, build_destinations, build_blog):
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

    leftover = [f"{p.relative_to(out_dir)}: {m.group(0)}"
                for p in sorted(out_dir.rglob("*")) if p.suffix in (".html", ".js")
                for m in _TOKEN_RE.finditer(p.read_text())]
    if leftover:
        raise BuildError(leftover, "Unfilled {{tokens}}")
    bad = check_links(out_dir, ["index.html"] + list(pages))
    if bad:
        raise BuildError(bad)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Build the BCH Taxi site.")
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
