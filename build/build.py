#!/usr/bin/env python3
"""Generate the BCH Taxi site from build/data.py and build/posts.py.

Usage:  python3 build/build.py

- Rewrites the marked regions of index.html (nav, tour cards, fares, modal, footer)
- Writes tours.html, tours/*.html, multi-day-tours.html, price-calculator.html,
  destinations.html, blog.html and blog/*.html
- Checks every local link and asset exists
"""
import html
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from data import *          # noqa: E402,F401
from posts import POSTS     # noqa: E402

E = html.escape
PARTIALS = Path(__file__).resolve().parent / "partials"
MODAL = (PARTIALS / "modal.html").read_text().strip()
FAB = (PARTIALS / "fab.html").read_text().strip()

TOUR_BY_SLUG = {t["slug"]: t for t in TOURS}


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
      <li class="nav-call"><a href="tel:{PHONE}">Call {PHONE_DISPLAY}</a></li>
      <li><a href="{idx(root, 'booking', is_index)}" class="nav-cta">Book Taxi</a></li>
    </ul>
    <div class="mobile-toggle" onclick="document.querySelector('.nav-links').classList.toggle('open')">
      <span></span><span></span><span></span>
    </div>
  </nav>"""


def footer(root, is_index=False):
    popular = [t for t in TOURS if t["fav"]] + [TOUR_BY_SLUG[s] for s in ("glendalough-wicklow", "connemara-galway", "dingle-peninsula")]
    tour_links = "\n".join(f'          <li><a href="{root}tours/{t["slug"]}.html">{E(t["name"])}</a></li>' for t in popular)
    return f"""  <footer class="site-footer">
    <div class="footer-grid">
      <div class="footer-about">
        <a href="{'#' if is_index else root + 'index.html'}" class="brand" aria-label="BCH Taxi home">
          {BRAND}
        </a>
        <p>Taxis, Dublin Airport transfers and private tours of Ireland in our wheelchair-accessible 8-seater. Available 24/7.</p>
        <ul class="footer-contact">
          <li><a href="tel:{PHONE}"><span>Call</span>{PHONE_DISPLAY}</a></li>
          <li><a href="{WHATSAPP}" target="_blank" rel="noopener"><span>WhatsApp</span>Message us</a></li>
          <li><a href="mailto:{EMAIL}"><span>Email</span>{EMAIL}</a></li>
        </ul>
      </div>
      <div>
        <h4>Explore</h4>
        <ul>
          <li><a href="{'#' if is_index else root + 'index.html'}">Home</a></li>
          <li><a href="{root}tours.html">Day Tours</a></li>
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
        <h4>Plan a Trip</h4>
        <p>Tell us your dates and where you'd like to go. We'll reply quickly with a fixed price.</p>
        <a href="{idx(root, 'booking', is_index)}" class="btn btn-gold">Book a Taxi</a>
        <a href="{root}price-calculator.html" class="btn btn-outline">Get a Quote</a>
      </div>
    </div>
    <div class="footer-bottom">
      <p>&copy; 2026 BCH Taxi. All rights reserved.</p>
      <p>Wheelchair-accessible 8-seater · Dublin, Meath &amp; all of Ireland</p>
    </div>
  </footer>"""


def fix_root(fragment, root):
    """Partials are written for the site root; point their links at `root`."""
    return fragment.replace('href="index.html', f'href="{root}index.html')


def page(*, root, title, description, body, active="", path="", jsonld=None, extra_js=""):
    canonical = ""
    if SITE_URL:
        canonical = f'\n  <link rel="canonical" href="{SITE_URL.rstrip("/")}/{path}">'
    ld = ""
    for block in (jsonld or []):
        ld += '\n  <script type="application/ld+json">\n' + json.dumps(block, ensure_ascii=False, indent=2) + "\n  </script>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{E(title)}</title>
  <meta name="description" content="{E(description)}">
  <meta name="robots" content="index, follow">
  <meta name="theme-color" content="#062a1f">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="BCH Taxi">
  <meta property="og:locale" content="en_IE">
  <meta property="og:title" content="{E(title)}">
  <meta property="og:description" content="{E(description)}">
  <meta property="og:image" content="{(SITE_URL.rstrip("/") + "/") if SITE_URL else root}images/hero.jpg">
  <meta name="twitter:card" content="summary_large_image">{canonical}
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%230a0a0a'/%3E%3Ctext x='32' y='42' font-family='Georgia,serif' font-size='26' font-weight='700' fill='%23c9a84c' text-anchor='middle'%3EBCH%3C/text%3E%3C/svg%3E">
  <link rel="apple-touch-icon" href="{root}images/logo.svg">
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
      <span class="hero-label">{E(label)}</span>
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

def tour_card(t, root, detail_link=True):
    li = "".join(f"<li>{E(x)}</li>" for x in t["highlights"][:4])
    extra = t["highlights"][4:]
    more = (f'<details class="tour-more"><summary>+{len(extra)} more</summary><ul class="tour-list">'
            + "".join(f"<li>{E(x)}</li>" for x in extra) + "</ul></details>") if extra else ""
    badge = '<span class="tour-badge">Most Popular</span>' if t["fav"] else ""
    details = f'<a class="tour-details" href="{root}tours/{t["slug"]}.html">View tour details →</a>' if detail_link else ""
    return f"""      <article class="tour-card reveal{' fav' if t['fav'] else ''}">
        {badge}
        <span class="tour-region">{E(t['region'])}</span>
        <h3><a href="{root}tours/{t['slug']}.html">{E(t['name'])}</a></h3>
        <div class="tour-chips"><span>{E(t['duration'])}</span><span>Private</span><span>Up to 8</span></div>
        <p>{E(t['desc'])}</p>
        <ul class="tour-list">{li}</ul>
        {more}
        {details}
        <div class="tour-foot">
          <div class="tour-price"><small>From</small>{eur(t['price'])}<span>per vehicle</span></div>
          <button type="button" class="btn btn-gold tour-book" data-price="{t['price']}" data-tour="{E(t['name'])}">Book</button>
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


def cta_band(root, title="Ready to book?", text="Send us your dates and we'll confirm availability and a fixed price, usually within the hour."):
    return f"""    <section class="cta-band theme-dark">
      <div class="reveal">
        <h2>{title}</h2>
        <p>{text}</p>
      </div>
      <div class="cta-actions reveal">
        <a href="{root}index.html#booking" class="btn btn-gold">Book a Taxi</a>
        <a href="{WHATSAPP}" class="btn btn-whatsapp" target="_blank" rel="noopener">WhatsApp Us</a>
        <a href="tel:{PHONE}" class="btn btn-outline">Call {PHONE_DISPLAY}</a>
      </div>
    </section>"""


def group_band(root, is_index=False):
    """Banner for groups bigger than one van."""
    book = (f'<button type="button" class="btn btn-gold" data-service="Group transport (9+)">Get a Group Quote</button>'
            if is_index else
            f'<a href="{root}index.html?service=Group%20transport%20(9%2B)#booking" class="btn btn-gold">Get a Group Quote</a>')
    return f"""  <section class="group-band theme-teal">
    <div class="group-inner reveal">
      <div class="group-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/></svg>
      </div>
      <div class="group-text">
        <span class="section-label">Large groups</span>
        <h2>More than {MAX_PASSENGERS} passengers? We've got you covered.</h2>
        <p>Weddings, school trips, sports teams, corporate events or a big family holiday: we can source extra vehicles, from a second van to a minibus or coach, so your whole group travels together. One booking, one point of contact.</p>
        <ul class="group-points">
          <li>Extra vans, minibuses or coaches</li>
          <li>Airport runs, tours and events</li>
          <li>One quote for the whole group</li>
        </ul>
      </div>
      <div class="group-actions">
        {book}
        <a href="{WHATSAPP}?text={quote("Hi BCH Taxi, I'd like a quote for a group of more than 8 people.")}" class="btn btn-whatsapp" target="_blank" rel="noopener">Ask on WhatsApp</a>
      </div>
    </div>
  </section>"""


INCLUDED = [
    "Private vehicle for your group only",
    "Up to 8 passengers, one price for the vehicle",
    "Bigger group? We can arrange extra vehicles",
    "Pickup and drop-off anywhere in Dublin or Meath",
    "Wheelchair-accessible van with ramp",
    "Flexible stops and pace on the day",
]


# ── Pages ────────────────────────────────────────────────────────────────────

def build_tour_pages():
    out = {}
    for t in TOURS:
        root = "../"
        crumbs = [("Home", "index.html"), ("Tours", "tours.html"), (t["name"], None)]
        others = [o for o in TOURS if o["area"] == t["area"] and o["slug"] != t["slug"]]
        others += [o for o in TOURS if o["fav"] and o["slug"] != t["slug"] and o not in others]
        hl = "".join(f"<li>{E(x)}</li>" for x in t["highlights"])
        inc = "".join(f"<li>{E(x)}</li>" for x in INCLUDED)
        body = page_hero(root, [(n, (root + h) if h else None) for n, h in crumbs], t["region"],
                         E(t["name"]) + " Private Tour",
                         E(t["desc"]),
                         f"""
      <div class="hero-meta">
        <span>{E(t['duration'])}</span><span>Private tour</span><span>Up to 8 passengers</span><span>From Dublin: {E(t['drive'])}</span>
      </div>""") + f"""

    <section class="theme-light tour-detail">
      <div class="detail-grid">
        <div class="detail-main">
          <h2>About this tour</h2>
          <p>{E(t['intro'])}</p>
          <h2>Highlights</h2>
          <ul class="check-list">{hl}</ul>
          <h2>What's included</h2>
          <ul class="check-list">{inc}</ul>
          <h2>Good to know</h2>
          <p>Every tour is private and fully flexible. Tell us where you're staying and anything you'd love to see, and we'll shape the day around you. Admission tickets for attractions are not included in the tour price.</p>
        </div>
        <aside class="book-card">
          <span class="tour-region">Private tour</span>
          <div class="tour-price"><small>From</small>{eur(t['price'])}<span>per vehicle · up to 8 people</span></div>
          <ul class="book-facts">
            <li><span>Duration</span>{E(t['duration'])}</li>
            <li><span>Drive from Dublin</span>{E(t['drive'])}</li>
            <li><span>Pickup</span>Dublin or Meath</li>
          </ul>
          <button type="button" class="btn btn-gold tour-book" data-price="{t['price']}" data-tour="{E(t['name'])}">Book This Tour</button>
          <a class="btn btn-whatsapp" href="{WHATSAPP}?text={quote(f"Hi BCH Taxi, I'd like to ask about the {t['name']} tour.")}" target="_blank" rel="noopener">Ask on WhatsApp</a>
          <a class="book-alt" href="{root}price-calculator.html?tour={t['slug']}">Add extras in the price calculator →</a>
          <p class="book-group">More than 8 people? <a href="{root}index.html?service=Group%20transport%20(9%2B)#booking">We can arrange extra vehicles.</a></p>
        </aside>
      </div>
    </section>

    <section class="theme-mint">
      <div class="reveal">
        <span class="section-label">More tours</span>
        <h2 class="section-title">You might also like</h2>
      </div>
      <div class="tours-grid">
{chr(10).join(tour_card(o, root) for o in others[:3])}
      </div>
    </section>

{group_band(root)}

{cta_band(root)}"""
        ld = [{
            "@context": "https://schema.org", "@type": "TouristTrip",
            "name": f"{t['name']} Private Tour", "description": t["desc"],
            "touristType": "Private group",
            "itinerary": {"@type": "ItemList", "itemListElement": [
                {"@type": "ListItem", "position": i, "name": h} for i, h in enumerate(t["highlights"], 1)]},
            "provider": {"@type": "TaxiService", "name": "BCH Taxi", "telephone": PHONE},
            "offers": {"@type": "Offer", "price": t["price"], "priceCurrency": "EUR",
                       "description": "Per vehicle, up to 8 passengers"},
        }, breadcrumb_ld([("Home", ""), ("Tours", "tours.html"), (t["name"], f"tours/{t['slug']}.html")])]
        out[f"tours/{t['slug']}.html"] = page(
            root=root, active="tours", path=f"tours/{t['slug']}.html", jsonld=ld,
            title=f"{t['name']} Private Tour from Dublin | {eur(t['price'])} per Vehicle | BCH Taxi",
            description=f"Private {t['name']} day tour from Dublin or Meath in a wheelchair-accessible 8-seater. {t['duration']}, from {eur(t['price'])} per vehicle for up to 8 people.",
            body=body)
    return out


def build_tours_hub():
    root = ""
    crumbs = [("Home", "index.html"), ("Tours", None)]
    body = page_hero(root, crumbs, "Private Day Tours", "Private Tours of Ireland",
                     "Twelve full-day private tours from Dublin and Meath in our 8-seater. One price covers the whole vehicle, so the more of you there are, the better the value.") + f"""

    <section class="theme-mint">
      <div class="tours-grid">
{chr(10).join(tour_card(t, root) for t in TOURS)}
      </div>
    </section>

    <section class="theme-light">
      <div class="split-promo reveal">
        <div>
          <span class="section-label">Longer trips</span>
          <h2 class="section-title">Multi-Day Tours</h2>
          <p class="section-desc">Keep the same driver and van for your whole trip, from {eur(MULTI_DAY_RATE)} per day. See our sample routes or plan your own.</p>
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
        description="12 private day tours from Dublin and Meath: Cliffs of Moher, Giant's Causeway, Ring of Kerry, Glendalough and more. Per-vehicle prices for up to 8 people.",
        body=body)}


def build_multi_day():
    root = ""
    crumbs = [("Home", "index.html"), ("Multi-Day Tours", None)]
    body = page_hero(root, crumbs, "Multi-Day Tours", "Multi-Day Private Tours of Ireland",
                     f"Your own driver and wheelchair-accessible 8-seater for the whole trip, from {eur(MULTI_DAY_RATE)} per day. Pick a sample route below or tell us what you'd like to see.") + f"""

    <section class="theme-mint">
      <div class="multi-grid">
{chr(10).join(multi_card(m, root) for m in MULTI_DAY)}
      </div>
      <div class="note-box reveal">
        <h3>How multi-day pricing works</h3>
        <ul class="check-list">
          <li>{eur(MULTI_DAY_RATE)} per day for the vehicle and driver, for up to 8 passengers.</li>
          <li>Accommodation, meals and attraction tickets are not included. We can suggest places to stay along the route.</li>
          <li>Routes are samples. We'll adjust the days, stops and pace to suit you.</li>
          <li>More than 8 travelling? We can arrange extra vehicles so the whole group tours together.</li>
        </ul>
        <a href="price-calculator.html" class="btn btn-gold">Price a Custom Trip</a>
      </div>
    </section>

{cta_band(root, "Plan your Ireland road trip", "Tell us your dates, group size and the places on your list, and we'll put together a route and a fixed price.")}"""
    return {"multi-day-tours.html": page(
        root=root, active="multi", path="multi-day-tours.html",
        jsonld=[breadcrumb_ld([("Home", ""), ("Multi-Day Tours", "multi-day-tours.html")])],
        title="Multi-Day Private Tours of Ireland | BCH Taxi",
        description=f"Private multi-day tours of Ireland with your own driver, from {eur(MULTI_DAY_RATE)} per day for up to 8 people. Sample routes: West Coast, Kerry, Causeway Coast and the Wild Atlantic Way.",
        body=body)}


def build_calculator():
    root = ""
    crumbs = [("Home", "index.html"), ("Price Calculator", None)]
    data = {
        "tours": [{"slug": t["slug"], "name": t["name"], "price": t["price"]} for t in TOURS],
        "multi": [{"slug": m["slug"], "name": m["name"], "days": m["days"]} for m in MULTI_DAY],
        "dayRate": MULTI_DAY_RATE, "hourRate": EXTRA_HOUR_RATE, "maxPax": MAX_PASSENGERS,
        "airport": [{"area": a, "to": to, "from": fr} for a, _, to, fr in AIRPORT_FARES]
                   + [{"area": a, "to": p, "from": p} for a, p in LONG_TRANSFERS],
    }
    tour_opts = "".join(f'<option value="{t["slug"]}">{E(t["name"])} · {eur(t["price"])}</option>' for t in TOURS)
    multi_opts = "".join(f'<option value="{m["slug"]}">{E(m["name"])} · {m["days"]} days</option>' for m in MULTI_DAY)
    air_opts = "".join(f'<option value="{i}">{E(a["area"])}</option>' for i, a in enumerate(data["airport"]))
    dial = re.search(r'<select name="dial".*?</select>', MODAL, re.S).group(0)
    body = page_hero(root, crumbs, "Instant Quote", "Tour &amp; Taxi Price Calculator",
                     "Pick a tour, a transfer or a multi-day trip and see your price instantly. Every price is for the whole vehicle, the same for 1 passenger or 8.") + f"""

    <section class="theme-light calc-section">
      <form class="calc" id="calc-form" novalidate>
        <div class="calc-main">
          <div class="calc-row">
            <div class="calc-row-head"><span class="calc-num">1</span><div><h3>Day tour</h3><p>A full-day private tour from Dublin or Meath.</p></div></div>
            <select id="calc-tour" name="tour" aria-label="Day tour"><option value="">No day tour</option>{tour_opts}</select>
          </div>
          <div class="calc-row">
            <div class="calc-row-head"><span class="calc-num">2</span><div><h3>Multi-day tour</h3><p>Same driver and van for the whole trip, {eur(MULTI_DAY_RATE)} per day.</p></div></div>
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
            <div class="calc-row-head"><span class="calc-num">3</span><div><h3>Airport transfer</h3><p>Fixed fares to and from Dublin Airport.</p></div></div>
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
            <div class="calc-row-head"><span class="calc-num">4</span><div><h3>Extra hours</h3><p>More time on any tour, {eur(EXTRA_HOUR_RATE)} per hour.</p></div></div>
            <div class="stepper">
              <button type="button" data-step="-1" aria-label="Fewer hours">−</button>
              <input id="calc-hours" name="hours" type="number" value="0" min="0" max="12" readonly aria-label="Extra hours">
              <button type="button" data-step="1" aria-label="More hours">+</button>
              <span class="stepper-unit">hours</span>
            </div>
          </div>
          <div class="calc-row">
            <div class="calc-row-head"><span class="calc-num">5</span><div><h3>Passengers</h3><p>Up to {MAX_PASSENGERS} in our van. It doesn't change the price.</p><p class="pax-more" hidden>More than {MAX_PASSENGERS}? We can arrange extra vehicles. Add your group size in the notes for a group quote.</p></div></div>
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
          <div class="calc-total"><span>Total</span><strong id="calc-total">€0</strong></div>
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
            <p class="form-legal">This is an estimate. We'll confirm a fixed price before anything is booked. Parking, tolls and attraction tickets may be extra.</p>
          </div>
        </aside>
      </form>
      <script id="calc-data" type="application/json">{json.dumps(data, ensure_ascii=False)}</script>
    </section>

    <section class="theme-mint">
      <div class="reveal">
        <span class="section-label">How it works</span>
        <h2 class="section-title">From estimate to fixed price</h2>
      </div>
      <div class="steps-grid">
        <div class="step-card reveal"><span class="calc-num">1</span><h3>Build your trip</h3><p>Combine a day tour, a multi-day trip, airport transfers and extra hours.</p></div>
        <div class="step-card reveal"><span class="calc-num">2</span><h3>See the price live</h3><p>The total updates as you choose. Prices are for the whole vehicle.</p></div>
        <div class="step-card reveal"><span class="calc-num">3</span><h3>Send it to us</h3><p>Send the quote by email or WhatsApp with your dates and pickup.</p></div>
        <div class="step-card reveal"><span class="calc-num">4</span><h3>Get a fixed price</h3><p>We confirm availability and a final fixed price. You pay on the day.</p></div>
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
        items = [t for t in TOURS if t["area"] == area]
        if not items:
            continue
        cards = "\n".join(f"""        <a class="dest-card reveal" href="tours/{t['slug']}.html">
          <span class="tour-region">{E(t['region'])}</span>
          <h3>{E(t['name'])}</h3>
          <p>{E(t['desc'])}</p>
          <span class="dest-meta"><span>From Dublin: {E(t['drive'])}</span><strong>{eur(t['price'])}</strong></span>
        </a>""" for t in items)
        groups.append(f"""      <div class="dest-group">
        <h2 class="dest-area">{E(area)}</h2>
        <div class="dest-grid">
{cards}
        </div>
      </div>""")
    body = page_hero(root, crumbs, "Destination Guide", "Where Can We Take You?",
                     "Ireland's best-loved places, grouped by region, with approximate driving times from Dublin. Tap any place to see the full tour.") + f"""

    <section class="theme-light">
{chr(10).join(groups)}
      <p class="tours-note">Driving times are approximate and depend on traffic and stops. Don't see your destination? <a href="index.html#booking">Ask us</a>, we go anywhere in Ireland.</p>
    </section>

{cta_band(root)}"""
    return {"destinations.html": page(
        root=root, active="tours", path="destinations.html",
        jsonld=[breadcrumb_ld([("Home", ""), ("Destinations", "destinations.html")])],
        title="Ireland Destination Guide: Day Trips & Driving Times from Dublin | BCH Taxi",
        description="Where to go in Ireland and how far it is from Dublin: Cliffs of Moher, Giant's Causeway, Ring of Kerry, Connemara, Glendalough and more, with private tour prices.",
        body=body)}


def fmt_date(d):
    import datetime
    return datetime.date.fromisoformat(d).strftime("%-d %B %Y")


def build_blog():
    out = {}
    root = ""
    cards = "\n".join(f"""        <a class="post-card reveal" href="blog/{p['slug']}.html">
          <span class="tour-region">{E(p['topic'])}</span>
          <h3>{E(p['title'])}</h3>
          <p>{E(p['summary'])}</p>
          <span class="post-meta">{fmt_date(p['date'])} · Read article →</span>
        </a>""" for p in POSTS)
    body = page_hero(root, [("Home", "index.html"), ("Blog", None)], "Travel Guides", "Ireland Travel Guides &amp; Tips",
                     "Day trip ideas, airport advice and practical tips for getting around Ireland.") + f"""

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
                         p["topic"], E(p["title"]), E(p["summary"]),
                         f'\n      <div class="hero-meta"><span>{fmt_date(p["date"])}</span><span>BCH Taxi</span></div>') + f"""

    <section class="theme-light">
      <article class="post-body">
{p['body'].replace('{ROOT}', root)}
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
        raise SystemExit(f"index.html is missing the @{name} marker")
    return pat.sub(lambda m: m.group(1) + "\n" + content + m.group(3), s, count=1)


def replace_inline(s, name, value):
    """Replace a value wrapped in inline markers: <!-- @name -->value<!-- /@name -->."""
    pat = re.compile(r"(<!-- @%s -->).*?(<!-- /@%s -->)" % (name, name), re.S)
    if not pat.search(s):
        raise SystemExit(f"index.html is missing the @{name} marker")
    return pat.sub(lambda m: m.group(1) + value + m.group(2), s)


def build_index():
    p = ROOT_DIR / "index.html"
    s = p.read_text()
    fares = "\n".join(
        f'        <div class="fare-row"><span class="fare-place">{E(a)}</span><span class="fare-km">{km}</span>'
        f'<span class="fare-price"><small>To airport</small>{eur(to)}</span><span class="fare-price"><small>From airport</small>{eur(fr)}</span></div>'
        for a, km, to, fr in AIRPORT_FARES)
    s = replace_region(s, "nav", nav("", is_index=True))
    s = replace_region(s, "tours-grid", "\n".join(tour_card(t, "") for t in TOURS))
    s = replace_region(s, "fares", fares)
    s = replace_region(s, "group-band", group_band("", is_index=True))
    s = replace_region(s, "fare-long", "\n".join(
        f'      <div class="fare-long-card"><span>Dublin Airport ⇄ {E(a)}</span><strong>{eur(p)}</strong></div>'
        for a, p in LONG_TRANSFERS))
    s = replace_inline(s, "min-fare", eur(min(to for _, _, to, _ in AIRPORT_FARES)) + "+")
    s, n = re.subn(r"day tours from €\d+(?:,\d{3})*", "day tours from " + eur(min(t["price"] for t in TOURS)), s)
    if not n:
        raise SystemExit("index.html meta description no longer mentions 'day tours from €…'")
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
    p.write_text(s)


# ── Link check ───────────────────────────────────────────────────────────────

def check_links(files):
    bad = []
    for rel in files:
        path = ROOT_DIR / rel
        text = path.read_text()
        for ref in re.findall(r'(?:href|src)="([^"]+)"', text) + re.findall(r"url\('([^']+)'\)", text):
            if re.match(r"^(https?:|mailto:|tel:|data:|#|javascript:)", ref):
                continue
            target = (path.parent / ref.split("#")[0].split("?")[0]).resolve()
            if not target.exists():
                bad.append(f"{rel}: {ref}")
    css = ROOT_DIR / "css" / "style.css"
    for ref in re.findall(r"url\('([^']+)'\)", css.read_text()):
        if not (css.parent / ref).resolve().exists():
            bad.append(f"css/style.css: {ref}")
    return bad


def main():
    pages = {}
    for builder in (build_tour_pages, build_tours_hub, build_multi_day, build_calculator, build_destinations, build_blog):
        pages.update(builder())
    for rel, content in pages.items():
        target = ROOT_DIR / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    build_index()

    if SITE_URL:
        urls = [""] + sorted(pages)
        base = SITE_URL.rstrip("/")
        xml = "\n".join(f"  <url><loc>{base}/{u}</loc></url>" for u in urls)
        (ROOT_DIR / "sitemap.xml").write_text(
            f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{xml}\n</urlset>\n')
        (ROOT_DIR / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")

    bad = check_links(["index.html"] + list(pages))
    print(f"Built {len(pages)} pages + index.html")
    if bad:
        print("Broken links:")
        for b in bad:
            print("  " + b)
        sys.exit(1)
    print("All local links OK")


if __name__ == "__main__":
    main()
