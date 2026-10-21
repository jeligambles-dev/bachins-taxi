import re
from pathlib import Path

import build
from content import default_content, merge


def _build_with_uploads(tmp_path, content, files):
    build.build_site(content, tmp_path,
                     extra_files={rel: b"\xff\xd8\xff" for rel in files})
    return tmp_path


def test_hero_slot_used(tmp_path):
    c = merge(default_content(), {"photo_slots": {"hero": "p1"}})
    c["_photos"] = {"p1": "uploads/abc.jpg"}
    _build_with_uploads(tmp_path, c, ["uploads/abc.jpg"])
    s = (tmp_path / "index.html").read_text()
    assert ".hero-bg{background-image:url('uploads/abc.jpg')}" in s
    assert '<link rel="preload" as="image" href="uploads/abc.jpg">' in s
    assert re.search(r'og:image" content="[^"]*uploads/abc\.jpg"', s)
    assert '"image": "images/hero.jpg"' not in s
    assert "images/hero.jpg" not in s.split("</head>")[0].replace(
        "web-production-95242.up.railway.app/images/hero.jpg", "")
    # sub-pages: og:image with the site URL prefix
    sub = (tmp_path / "tours/ring-of-kerry.html").read_text()
    assert re.search(r'og:image" content="https?://[^"]*/uploads/abc\.jpg"', sub)


def test_hero_slot_relative_without_site_url(tmp_path):
    c = merge(default_content(), {"photo_slots": {"hero": "p1"},
                                  "settings": {"site_url": ""}})
    c["_photos"] = {"p1": "uploads/abc.jpg"}
    _build_with_uploads(tmp_path, c, ["uploads/abc.jpg"])
    sub = (tmp_path / "tours/ring-of-kerry.html").read_text()
    assert 'og:image" content="../uploads/abc.jpg"' in sub


def test_hero_slot_absolute_with_site_url(tmp_path):
    c = merge(default_content(), {"photo_slots": {"hero": "p1"},
                                  "settings": {"site_url": "https://x.example/"}})
    c["_photos"] = {"p1": "uploads/abc.jpg"}
    _build_with_uploads(tmp_path, c, ["uploads/abc.jpg"])
    s = (tmp_path / "index.html").read_text()
    assert 'og:image" content="https://x.example/uploads/abc.jpg"' in s
    assert '"image": "https://x.example/uploads/abc.jpg"' in s
    assert 'rel="preload" as="image" href="uploads/abc.jpg"' in s


def test_taxi_and_logo_slots(tmp_path):
    c = merge(default_content(), {"photo_slots": {"taxi": "t1", "logo": "l1"}})
    c["_photos"] = {"t1": "uploads/taxi1.jpg", "l1": "uploads/logo1.png"}
    _build_with_uploads(tmp_path, c, ["uploads/taxi1.jpg", "uploads/logo1.png"])
    s = (tmp_path / "index.html").read_text()
    assert '<img src="uploads/taxi1.jpg"' in s
    assert 'images/taxi.jpg' not in s
    assert 'rel="apple-touch-icon" href="uploads/logo1.png"' in s
    assert '"logo": "' in s and "uploads/logo1.png" in s
    sub = (tmp_path / "blog.html").read_text()
    assert 'rel="apple-touch-icon" href="uploads/logo1.png"' in sub
    t = (tmp_path / "tours/ring-of-kerry.html").read_text()
    assert 'rel="apple-touch-icon" href="../uploads/logo1.png"' in t


def test_tour_photo_card_and_page(tmp_path):
    c = merge(default_content(), {})
    c["tours"] = [dict(t, photo="k1") if t["slug"] == "ring-of-kerry" else t
                  for t in c["tours"]]
    c["_photos"] = {"k1": "uploads/kerry1.jpg"}
    _build_with_uploads(tmp_path, c, ["uploads/kerry1.jpg"])
    idx = (tmp_path / "index.html").read_text()
    card = re.search(r'<article class="tour-card.*?</article>',
                     idx[idx.index('href="tours/ring-of-kerry.html"') - 600:], re.S).group(0)
    assert 'src="uploads/kerry1.jpg"' in card and 'loading="lazy"' in card
    assert idx.count("uploads/kerry1.jpg") == 1
    page = (tmp_path / "tours/ring-of-kerry.html").read_text()
    assert 'src="../uploads/kerry1.jpg"' in page
    assert page.index("../uploads/kerry1.jpg") < page.index("<h2>About")


def test_no_photo_unchanged(tmp_path):
    build.build_site(merge(default_content(), {}), tmp_path)
    for p in tmp_path.rglob("*.html"):
        assert "uploads/" not in p.read_text(), p
    assert "images/taxi.jpg" in (tmp_path / "index.html").read_text()


def test_missing_or_invalid_photo_ids_are_unset(tmp_path):
    c = merge(default_content(), {"photo_slots": {"hero": "nope", "taxi": "bad"}})
    c["_photos"] = {"bad": "../../etc/passwd.jpg"}
    build.build_site(c, tmp_path)
    s = (tmp_path / "index.html").read_text()
    assert "uploads/" not in s and "etc/passwd" not in s


def test_generator_uses_photo_paths_verbatim(tmp_path):
    c = merge(default_content(), {"photo_slots": {"hero": "slotname"}})
    c["_photos"] = {"slotname": "uploads/0123abcdef.png"}
    _build_with_uploads(tmp_path, c, ["uploads/0123abcdef.png"])
    s = (tmp_path / "index.html").read_text()
    assert "uploads/0123abcdef.png" in s
    assert "uploads/hero" not in s and "uploads/slotname" not in s


def test_owner_braces_render_literally(tmp_path):
    c = merge(default_content(), {})
    c["tours"] = [dict(t, name="A {{FOO}} B {{PHONE}}") if t["slug"] == "ring-of-kerry" else t
                  for t in c["tours"]]
    build.build_site(c, tmp_path)
    page = (tmp_path / "tours/ring-of-kerry.html").read_text()
    assert "A &#123;{FOO}} B &#123;{PHONE}}" in page
    assert "{{FOO}}" not in page and "{{PHONE}}" not in page
    for f in ("index.html", "tours.html", "price-calculator.html"):
        assert "{{FOO}}" not in (tmp_path / f).read_text()
    # contact tokens elsewhere are still filled
    assert "tel:" in page and "{{" not in page


def test_script_breakout_escaped(tmp_path):
    c = merge(default_content(), {})
    c["tours"] = [dict(t, name="X</script><i>Z") if t["slug"] == "ring-of-kerry" else t
                  for t in c["tours"]]
    c["photo_slots"]["hero"] = ["corrupt"]
    build.build_site(c, tmp_path)
    for p in tmp_path.rglob("*.html"):
        assert "</script><i>" not in p.read_text(), p
    assert "\\u003c/script" in (tmp_path / "price-calculator.html").read_text()
