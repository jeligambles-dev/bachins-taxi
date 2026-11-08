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
