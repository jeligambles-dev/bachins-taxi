import json
import re
from pathlib import Path

import pytest

import build
from content import default_content, merge


def _tour_patch(**by_slug):
    base = default_content()
    tours = []
    for t in base["tours"]:
        t = dict(t)
        t.update(by_slug.get(t["slug"], {}))
        tours.append(t)
    return merge(base, {"tours": tours})


def _build(tmp_path, content):
    build.build_site(content, tmp_path)
    return tmp_path


def _all_text(root):
    return {p.relative_to(root).as_posix(): p.read_text()
            for p in Path(root).rglob("*") if p.suffix in (".html", ".xml", ".js")}


def _footer(text):
    return text[text.index('<footer class="site-footer">'):]


def test_pub_and_golf_listing_pages(tmp_path):
    _build(tmp_path, merge(default_content(), {}))
    assert "Boyne Valley Pub Trail" in (tmp_path / "pub-tours.html").read_text()
    assert "Dublin Links Golf Day" in (tmp_path / "golf-trips.html").read_text()
    assert (tmp_path / "tours/meath-boyne-pub-trail.html").exists()
    tours = (tmp_path / "tours.html").read_text()
    assert "Boyne Valley Pub Trail" not in tours
    assert "Dublin Links Golf Day" not in tours
    idx = (tmp_path / "index.html").read_text()
    assert "Boyne Valley Pub Trail" in idx and "Dublin Links Golf Day" in idx
    assert idx.index("Ring of Kerry") < idx.index("Boyne Valley Pub Trail") < idx.index("Dublin Links Golf Day")


def test_unpriced_tour_everywhere(tmp_path):
    _build(tmp_path, _tour_patch(**{"ring-of-kerry": {"price": None}}))
    texts = _all_text(tmp_path)
    for rel, text in texts.items():
        for bad in ("€0", "€None", "€X"):
            assert bad not in text, (rel, bad)
    page = texts["tours/ring-of-kerry.html"]
    title = re.search(r"<title>(.*?)</title>", page).group(1)
    assert "€" not in title
    ld = "".join(re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S))
    assert '"offers"' not in ld
    calc = re.search(r'id="calc-data" type="application/json">(.*?)</script>',
                     texts["price-calculator.html"], re.S).group(1)
    assert "ring-of-kerry" not in calc
    assert "Price on request" in texts["destinations.html"]
    assert 'data-price=""' in texts["index.html"]
    assert "from €" not in re.search(r'name="description" content="(.*?)"', page).group(1)


def test_all_tours_unpriced_builds(tmp_path):
    base = default_content()
    tours = [dict(t, price=None) for t in base["tours"]]
    _build(tmp_path, merge(base, {"tours": tours}))
    idx = (tmp_path / "index.html").read_text()
    assert "day tours from €" not in idx or "€None" not in idx
    assert (tmp_path / "tours.html").exists()


def test_hidden_tour_excluded(tmp_path):
    _build(tmp_path, _tour_patch(**{"cliffs-of-moher": {"published": False}}))
    page = (tmp_path / "tours/cliffs-of-moher.html").read_text()
    assert '<meta name="robots" content="noindex">' in page
    assert 'content="index, follow"' not in page
    for rel in ("tours.html", "index.html", "sitemap.xml", "destinations.html"):
        assert "cliffs-of-moher" not in (tmp_path / rel).read_text(), rel
    assert "cliffs-of-moher" not in _footer((tmp_path / "blog.html").read_text())
    calc = (tmp_path / "price-calculator.html").read_text()
    assert "cliffs-of-moher" not in calc
    for slug, p in {s: (tmp_path / f"tours/{s}.html").read_text()
                    for s in ("ring-of-kerry", "dingle-peninsula")}.items():
        sec = p[p.index("You might also like"):]
        assert "cliffs-of-moher" not in sec


def test_footer_survives_missing_hardcoded_slugs(tmp_path):
    slugs = ("glendalough-wicklow", "connemara-galway", "dingle-peninsula")
    _build(tmp_path, _tour_patch(**{s: {"published": False} for s in slugs}))
    for rel, text in _all_text(tmp_path).items():
        if rel.endswith(".html") and "<footer" in text:
            foot = _footer(text)
            for s in slugs:
                assert f"tours/{s}.html" not in foot, (rel, s)


def test_golf_price_unit(tmp_path):
    _build(tmp_path, _tour_patch(**{"dublin-links-golf-day": {"price": 900}}))
    page = (tmp_path / "tours/dublin-links-golf-day.html").read_text()
    assert "€900" in page and "per trip" in page
    assert "Golf Trip" in page
    assert "Room for clubs and bags" in page
    assert "price-calculator.html?tour=" not in page
    listing = (tmp_path / "golf-trips.html").read_text()
    assert "€900" in listing and "per trip" in listing


def test_pub_detail_page(tmp_path):
    _build(tmp_path, merge(default_content(), {}))
    page = (tmp_path / "tours/meath-boyne-pub-trail.html").read_text()
    assert "Rural Pub Tour" in page
    assert "Your driver gets everyone home safely" in page
    assert 'href="../pub-tours.html"' in page
    assert "Price on request" in page
    day = (tmp_path / "tours/ring-of-kerry.html").read_text()
    assert "price-calculator.html?tour=ring-of-kerry" in day


def test_nav_and_footer_have_new_pages(tmp_path):
    _build(tmp_path, merge(default_content(), {}))
    for rel in ("index.html", "tours.html", "golf-trips.html"):
        text = (tmp_path / rel).read_text()
        assert "pub-tours.html" in text and "golf-trips.html" in text
    assert 'aria-current="page">Golf<' in (tmp_path / "golf-trips.html").read_text()


def test_service_dropdowns_have_new_trips(tmp_path):
    _build(tmp_path, merge(default_content(), {}))
    idx = (tmp_path / "index.html").read_text()
    for sel in ("cf-service",):   # the quick-book widget was merged into the booking card
        block = re.search(r'<select id="%s".*?</select>' % sel, idx, re.S).group(0)
        assert "<option>Rural pub tour</option>" in block
        assert "<option>Golf trip</option>" in block


def test_missing_marker_raises_builderror(tmp_path, monkeypatch):
    tpl = tmp_path / "tpl.html"
    tpl.write_text("<html>no markers</html>")
    monkeypatch.setattr(build, "TEMPLATE_INDEX", tpl)
    with pytest.raises(build.BuildError):
        build.build_site(merge(default_content(), {}), tmp_path / "out")


def test_out_dir_guard_refuses_repo_paths(tmp_path):
    victim = build.ROOT_DIR / "css"
    before = sorted(p.name for p in victim.iterdir())
    with pytest.raises(ValueError):
        build.build_site(merge(default_content(), {}), victim)
    assert sorted(p.name for p in victim.iterdir()) == before
    with pytest.raises(ValueError):
        build.build_site(merge(default_content(), {}), build.ROOT_DIR / "build" / "x")
