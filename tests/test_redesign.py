"""Dark executive redesign (docs/superpowers/specs/2026-11-08-dark-executive-redesign-design.md)."""
from pathlib import Path

import build
from content import default_content, merge


def _build(tmp_path, content=None):
    build.build_site(content or merge(default_content(), {}), tmp_path)
    return tmp_path


def test_every_page_loads_serif_font(tmp_path):
    _build(tmp_path)
    pages = list(Path(tmp_path).rglob("*.html"))
    assert len(pages) > 10
    for p in pages:
        head = p.read_text().split("</head>")[0]
        assert "family=Instrument+Serif" in head, p
        assert "family=Geist" in head, p


def _hero(tmp_path, content=None):
    h = (_build(tmp_path, content) / "index.html").read_text()
    return h[h.index('<section class="hero">'):h.index("</section>", h.index('<section class="hero">'))]


def test_hero_new_defaults(tmp_path):
    hero = _hero(tmp_path)
    assert "Arrive the way" in hero
    assert "you planned." in hero
    assert "Private transport · Ireland" in hero
    assert 'class="hero-eyebrow"' in hero


def test_hero_eyebrow_is_editable():
    import texts
    assert "home.hero_eyebrow" in texts.all_text_defaults()


def test_hero_owner_override_wins(tmp_path):
    c = merge(default_content(), {"texts": {
        "home.hero_title": "Our own very long headline that goes on and on",
        "home.hero_eyebrow": "Meath & Dublin"}})
    hero = _hero(tmp_path, c)
    assert "Our own very long headline that goes on and on" in hero
    assert "Meath &amp; Dublin" in hero
    assert "Arrive the way" not in hero


# ── Homepage fleet showcase ────────────────────────────────────────────────
import re

from content import normalize_vehicle


def _showcase(tmp_path, content=None):
    h = (_build(tmp_path, content) / "index.html").read_text()
    s = h[h.index('id="fleet-strip"'):]
    return s[:s.index("</section>")]


def _items(sc):
    """{slug: html} for each showcase item."""
    parts = re.split(r'(?=<article class="showcase-item)', sc)[1:]
    return {re.search(r'data-vehicle="([^"]+)"', p).group(1): p for p in parts}


def _min_tour_price(content):
    build._configure(content)
    return min(t["price"] for t in build.published() if t["price"] is not None)


def test_showcase_features_van(tmp_path):
    sc = _showcase(tmp_path)
    assert sc.count('class="showcase-item is-featured"') == 1
    assert sc.count('<article class="showcase-item') == 4
    assert "8-seater" in _items(sc)["van"] and "is-featured" in _items(sc)["van"]
    tabs = sc[sc.index('class="showcase-tabs"'):]
    assert tabs.count("data-vehicle=") == 4


def test_showcase_van_from_price(tmp_path):
    c = merge(default_content(), {})
    sc = _showcase(tmp_path, c)
    items = _items(sc)
    assert "Tours from " + build.eur(_min_tour_price(c)) in items["van"]
    saloon = next(v for v in c["fleet"] if v["slug"] == "saloon")
    assert saloon["price_note"] and build.E(saloon["price_note"]) in items["saloon"]
    assert "Tours from" not in items["saloon"]


def test_showcase_book_link(tmp_path):
    items = _items(_showcase(tmp_path))
    assert len(items) == 4
    for slug, html in items.items():
        assert f'index.html?vehicle={slug}#booking' in html
        assert "Book this vehicle" in html


def test_showcase_van_hidden(tmp_path):
    c = merge(default_content(), {})
    for v in c["fleet"]:
        if v["slug"] == "van":
            v["published"] = False
    sc = _showcase(tmp_path, c)
    first = next(v["slug"] for v in c["fleet"] if v["published"])
    assert "is-featured" in _items(sc)[first]
    assert "Tours from" not in sc


def test_showcase_single_vehicle_no_tabs(tmp_path):
    c = merge(default_content(), {"fleet": [normalize_vehicle({"slug": "van", "name": "8-seater van", "passengers": 8})]})
    sc = _showcase(tmp_path, c)
    assert 'class="showcase-tabs"' not in sc and sc.count('<article class="showcase-item') == 1


def test_showcase_empty_fleet_builds(tmp_path):
    c = merge(default_content(), {"fleet": []})
    h = (_build(tmp_path, c) / "index.html").read_text()
    assert "showcase-item" not in h


def test_showcase_no_priced_tours(tmp_path):
    c = merge(default_content(), {})
    for t in c["tours"]:
        t["price"] = None
    van = next(v for v in c["fleet"] if v["slug"] == "van")
    van["price_note"] = "Ask for a price"
    item = _items(_showcase(tmp_path, c))["van"]
    assert "Tours from" not in item and "Ask for a price" in item


def test_showcase_no_photo_panel(tmp_path):
    c = merge(default_content(), {"fleet": [
        normalize_vehicle({"slug": "zz-no-photo", "name": "Plain Car", "passengers": 2}),
        normalize_vehicle({"slug": "van", "name": "8-seater van", "passengers": 8})]})
    assert "fleet-panel" in _items(_showcase(tmp_path, c))["zz-no-photo"]


def test_showcase_escapes_owner_text(tmp_path):
    c = merge(default_content(), {"fleet": [
        normalize_vehicle({"slug": "van", "name": "<script>x", "passengers": 8, "features": ["<b>f</b>"]})]})
    sc = _showcase(tmp_path, c)
    assert "showcase-item" in sc
    assert "<script>x" not in sc and "&lt;script&gt;x" in sc and "<b>f</b>" not in sc


def test_showcase_wheelchair_access_cell(tmp_path):
    item = _items(_showcase(tmp_path))["van"]
    assert "Ramp" in item


# ── Fleet page spec sheets ─────────────────────────────────────────────────

def test_fleet_page_spec_sheets(tmp_path):
    c = merge(default_content(), {})
    h = (_build(tmp_path, c) / "fleet.html").read_text()
    n = len([v for v in c["fleet"] if v["published"]])
    parts = re.split(r'(?=<article class="[^"]*fleet-sheet)', h)[1:]
    assert len(parts) == n == 4
    for p in parts:
        assert 'class="spec-grid"' in p


def test_access_cell_ignores_negative_wheelchair_note(tmp_path):
    c = merge(default_content(), {"fleet": [normalize_vehicle(
        {"slug": "saloon", "name": "Saloon", "passengers": 3,
         "features": ["Not wheelchair accessible", "Air conditioning"]})]})
    item = _items(_showcase(tmp_path, c))["saloon"]
    assert "Ramp" not in item
    assert "Not wheelchair accessible" in item


# ── Logo ───────────────────────────────────────────────────────────────────

def test_logo_in_header_and_footer_on_every_page(tmp_path):
    _build(tmp_path)
    for p in Path(tmp_path).rglob("*.html"):
        h = p.read_text()
        depth = len(p.relative_to(tmp_path).parts) - 1
        src = "../" * depth + "images/logo.png"
        nav = h[h.index('class="site-nav'):h.index("</nav>")] if 'class="site-nav' in h else ""
        foot = h[h.index('class="site-footer'):]
        for part, name in ((nav, "header"), (foot, "footer")):
            assert f'<img class="brand-logo" src="{src}" alt="BCH Taxi"' in part, (p, name)


def test_logo_files_exist_and_icon_is_500px():
    from PIL import Image
    root = Path(build.__file__).resolve().parent.parent / "images"
    assert (root / "logo.png").is_file()
    with Image.open(root / "logo-500.png") as im:
        assert im.size == (500, 500)


def test_apple_touch_icon_uses_square_logo(tmp_path):
    _build(tmp_path)
    for rel in ("index.html", "fleet.html"):
        assert 'rel="apple-touch-icon" href="images/logo-500.png"' in (tmp_path / rel).read_text(), rel
