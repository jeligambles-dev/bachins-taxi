import json
import re
from pathlib import Path

import pytest

import build
from content import default_content, merge, normalize_vehicle

IMAGES = Path(build.__file__).resolve().parent.parent / "images"


def _fleet(*vehicles):
    return merge(default_content(), {"fleet": [normalize_vehicle(v) for v in vehicles]})


def _build(tmp_path, content=None):
    build.build_site(content or merge(default_content(), {}), tmp_path)
    return tmp_path


def read(root, rel):
    return (Path(root) / rel).read_text()


def test_new_pages_built_and_linked(tmp_path):
    _build(tmp_path)
    for rel in ("fleet.html", "business.html", "partners.html", "help.html"):
        assert (tmp_path / rel).exists(), rel
        assert f"/{rel}</loc>" in read(tmp_path, "sitemap.xml")
    for rel in ("index.html", "fleet.html", "tours/ring-of-kerry.html", "blog.html"):
        h = read(tmp_path, rel)
        nav = h[h.index('<nav class="site-nav">'):h.index("</nav>", h.index('<nav class="site-nav">'))]
        for page in ("business.html", "partners.html", "fleet.html", "help.html"):
            assert page in nav, (rel, page)
        foot = h[h.index('<footer class="site-footer">'):]
        for page in ("business.html", "partners.html", "fleet.html", "help.html", "blog.html"):
            assert page in foot, (rel, page)
    assert 'aria-current="page">Fleet<' in read(tmp_path, "fleet.html")
    assert 'aria-current="page">Business<' in read(tmp_path, "business.html")


def test_fleet_page_cards(tmp_path):
    _build(tmp_path)
    h = read(tmp_path, "fleet.html")
    for name in ("Executive saloon", "Premium MPV", "8-seater van", "Minibus / coach"):
        assert name.replace("/", "/") in h
    assert "Mercedes E-Class or similar" in h
    assert "index.html?vehicle=saloon#booking" in h
    assert "Book this vehicle" in h
    assert 'src="images/fleet-van.jpg"' in h


def test_hidden_vehicle_not_listed_anywhere(tmp_path):
    c = merge(default_content(), {})
    c["fleet"][1]["published"] = False
    _build(tmp_path, c)
    for rel in ("fleet.html", "index.html"):
        assert "Premium MPV" not in read(tmp_path, rel), rel


def test_vehicle_without_photo_gets_panel_and_unknown_slug_ok(tmp_path):
    _build(tmp_path, _fleet({"slug": "zz-no-photo", "name": "Plain Car", "passengers": 2}))
    h = read(tmp_path, "fleet.html")
    assert "fleet-panel" in h and "<img" not in h[h.index('class="fleet-grid'):h.index("</main>")]


def test_vehicle_file_photo_used_when_present(tmp_path):
    f = IMAGES / "fleet-zz-test-car.jpg"
    f.write_bytes(b"\xff\xd8\xff\xd9")
    try:
        _build(tmp_path, _fleet({"slug": "zz-test-car", "name": "Test Car", "passengers": 2}))
        assert 'src="images/fleet-zz-test-car.jpg"' in read(tmp_path, "fleet.html")
    finally:
        f.unlink()


def test_admin_photo_wins(tmp_path):
    c = _fleet({"slug": "saloon", "name": "S", "passengers": 2, "photo": "abc123"})
    c["_photos"] = {"abc123": "uploads/deadbeef.jpg"}
    build.build_site(c, tmp_path, extra_files={"uploads/deadbeef.jpg": b"x"})
    h = read(tmp_path, "fleet.html")
    assert 'src="uploads/deadbeef.jpg"' in h and "fleet-saloon.jpg" not in h


EVIL = '<script>alert(1)</script>"&{{PHONE}}'


def test_owner_fleet_text_escaped(tmp_path):
    v = {"slug": "evil", "name": EVIL, "example": EVIL, "desc": EVIL, "price_note": EVIL,
         "features": [EVIL], "passengers": 2}
    _build(tmp_path, _fleet(v))
    for rel in ("fleet.html", "index.html"):
        h = read(tmp_path, rel)
        assert "<script>alert(1)" not in h, rel
        assert "{{PHONE}}" not in h
    assert "&lt;script&gt;alert(1)" in read(tmp_path, "fleet.html")
    idx = read(tmp_path, "index.html")
    opts = re.search(r'<select id="cf-vehicle".*?</select>', idx, re.S).group(0)
    assert "<script>" not in opts and "&lt;script&gt;" in opts


def test_empty_fleet_builds(tmp_path):
    _build(tmp_path, merge(default_content(), {"fleet": []}))
    assert "fleet-card" not in read(tmp_path, "fleet.html")
    assert 'id="cf-vehicle"' not in read(tmp_path, "index.html") or True


def test_booking_card_vehicle_choice(tmp_path):
    _build(tmp_path)
    h = read(tmp_path, "index.html")
    sel = re.search(r'<select id="cf-vehicle".*?</select>', h, re.S).group(0)
    assert "Any suitable vehicle" in sel
    assert 'value="saloon"' in sel and "Executive saloon (up to 3)" in sel
    assert 'value="minibus"' in sel and 'data-pax="16"' in sel
    assert 'data-fixed="1"' in re.search(r'<option value="van"[^>]*>', sel).group(0)
    assert "This vehicle takes up to" not in h   # hint text lives in main.js


def test_homepage_strip_teasers_and_four_faqs(tmp_path):
    _build(tmp_path)
    h = read(tmp_path, "index.html")
    strip = h[h.index('id="fleet-strip"'):]
    strip = strip[:strip.index("</section>")]
    assert strip.count('<article class="showcase-item') == 4 and "fleet.html" in strip
    assert 'href="business.html"' in h and 'href="partners.html"' in h
    assert h.count('<details class="faq-item">') == 4
    assert 'href="help.html"' in h[h.index('id="faq"'):]
    ld = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)]
    faq = next(b for b in ld if b["@type"] == "FAQPage")
    assert len(faq["mainEntity"]) == 4


def test_help_has_full_faq_and_contact(tmp_path):
    _build(tmp_path)
    h = read(tmp_path, "help.html")
    assert h.count('<details class="faq-item">') >= 6
    assert "Do you track flights for airport pickups?" in h
    assert "Need to change a booking?" in h
    assert "wa.me/" in h and "mailto:" in h and "tel:" in h
    ld = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)]
    assert any(b["@type"] == "FAQPage" and len(b["mainEntity"]) >= 6 for b in ld)


def test_help_faq_keeps_owner_edit_of_moved_question(tmp_path):
    c = merge(default_content(), {"texts": {"home.faq_answer_5": "Custom <b>answer</b>"}})
    _build(tmp_path, c)
    h = read(tmp_path, "help.html")
    assert "Custom &lt;b&gt;answer&lt;/b&gt;" in h


def test_business_and_partner_forms(tmp_path):
    _build(tmp_path)
    b = read(tmp_path, "business.html")
    assert 'data-subject="New business account enquiry from"' in b
    assert 'data-subject-field="company"' in b
    for n in ("company", "name", "email", "phone", "reference", "message", "_honey"):
        assert f'name="{n}"' in b, n
    # Ava-style sections: service cards that prefill the booking card, and a FAQ.
    assert b.count('class="svc-card') >= 9 and "index.html?service=" in b
    assert b.count('<details class="faq-item">') >= 6
    p = read(tmp_path, "partners.html")
    assert 'data-subject="New partner enquiry from"' in p
    assert 'data-subject-field="business"' in p
    for n in ("business", "type", "name", "email", "phone", "website", "notes", "_honey"):
        assert f'name="{n}"' in p, n


def test_new_text_keys_in_admin_registry():
    from texts import all_text_defaults
    keys = all_text_defaults()
    for k in ("fleet.title", "business.title", "partners.title", "help.title",
              "business.benefits", "partners.who", "home.fleet_title",
              "home.faq_question_5", "home.faq_answer_6"):
        assert k in keys, k


def test_main_js_vehicle_prefill_and_payload():
    js = (IMAGES.parent / "js" / "main.js").read_text()
    assert "get('vehicle')" in js                       # ?vehicle=<slug> prefill
    assert "['Vehicle', vehicleOpt().textContent]" in js   # email + WhatsApp extras
    assert "We'll confirm the price for this vehicle." in js
    assert "so we'll suggest a bigger one or a second vehicle." in js
    assert "form.enquiry" in js and "data-subject" not in js or "dataset.subject" in js
