import json
import re
from pathlib import Path

import build
import texts
from content import default_content, merge

NEW = {"email": "new@x.ie", "phone": "+353861112222",
       "phone_display": "+353 86 111 2222", "whatsapp_number": "353861112222"}
OLD = ("bachintaxi@gmail.com", "0330046", "353870330046")


def _content(texts_=None, settings=None):
    stored = {}
    if texts_:
        stored["texts"] = texts_
    if settings:
        stored["settings"] = settings
    return merge(default_content(), stored)


def _all_text(out):
    for p in Path(out).rglob("*"):
        if p.is_file() and p.suffix in (".html", ".js", ".xml", ".txt", ".json"):
            yield p, p.read_text()


def test_text_override_on_index_and_subpage(tmp_path):
    build.build_site(_content({"home.hero_title": "Hello <b>",
                               "footer.about": "About us"}), tmp_path)
    assert "Hello &lt;b&gt;" in (tmp_path / "index.html").read_text()
    assert "<b>" not in (tmp_path / "index.html").read_text().split("<h1>")[1].split("</h1>")[0]
    assert "About us" in (tmp_path / "tours.html").read_text()


def test_markers_stripped(tmp_path):
    build.build_site(_content(), tmp_path)
    for p, text in _all_text(tmp_path):
        assert "<!-- @t:" not in text and "<!-- /@t:" not in text, p


def test_every_template_marker_has_default():
    found = texts.template_texts(build.TEMPLATE_INDEX.read_text())
    assert len(found) >= 60
    assert all(v.strip() for v in found.values())


def test_registry_covers_build_py_copy():
    d = texts.all_text_defaults()
    for key in ("tours.lead", "footer.about", "cta.text", "included.day",
                "included.pub", "included.golf", "good_to_know.golf"):
        assert key in d, key
    assert d["included.day"]["multiline"] is True
    assert d["home.hero_title"]["group"] == "Home page"
    assert all(v["default"].strip() for v in d.values())


def test_included_override_lines(tmp_path):
    build.build_site(_content({"included.golf": "Clubs\n\nBags & more"}), tmp_path)
    page = (tmp_path / "golf-trips.html").read_text()
    assert "<li>Clubs</li><li>Bags &amp; more</li>" in page


def test_default_build_text_matches_before(tmp_path):
    build.build_site(_content(), tmp_path)
    s = (tmp_path / "index.html").read_text()
    assert "Taxis, Airport Runs &amp; <span class=\"gold\">Private Tours of Ireland</span>" in s
    assert "How far in advance should I book?" in s
    assert "For airport transfers and early morning pickups, we recommend booking at least 24 hours in advance." in s


def test_contact_change_everywhere(tmp_path):
    build.build_site(_content(settings=NEW), tmp_path)
    for p, text in _all_text(tmp_path):
        for old in OLD:
            assert old not in text, (p, old)
    s = (tmp_path / "index.html").read_text()
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', s, re.S)
    docs = [json.loads(b) for b in blocks]
    assert docs[0]["email"] == "new@x.ie"
    assert docs[0]["telephone"] == "+353861112222"
    assert "new@x.ie" in (tmp_path / "js" / "config.js").read_text()
    assert "https://wa.me/353861112222" in s
    assert 'href="tel:+353861112222"' in s
    assert "No {{" not in s and "{{" not in s


def test_contact_values_escaped(tmp_path):
    build.build_site(_content(settings={"email": 'a"b@x.ie'}), tmp_path)
    s = (tmp_path / "index.html").read_text()
    assert 'a"b@x.ie' not in s.split("<body")[1]
    assert "{{" not in s


def test_config_js_cache_busted(tmp_path):
    def version(settings, sub):
        out = tmp_path / sub
        build.build_site(_content(settings=settings), out)
        m = re.search(r"js/config\.js\?v=([0-9a-f]{8})", (out / "index.html").read_text())
        return m.group(1), (out / "tours" / "ring-of-kerry.html").read_text()
    a, _ = version(None, "a")
    b, sub = version({"email": "other@x.ie"}, "b")
    assert a != b
    assert f'../js/config.js?v={b}' in sub
    assert sub.index("config.js") < sub.index("main.js")


def test_main_js_tolerates_missing_config():
    js = (Path(build.__file__).resolve().parent.parent / "js" / "main.js").read_text()
    assert "window.BCH ||" in js
    assert "bachintaxi" not in js and "353870330046" not in js


def test_texts_with_braces_cannot_forge_tokens(tmp_path):
    build.build_site(_content({"footer.about": "x {{PHONE}} y"}), tmp_path)
    assert "{{PHONE}}" not in (tmp_path / "tours.html").read_text()


def test_faq_override_updates_jsonld(tmp_path):
    build.build_site(_content({"home.faq_question_3": 'Cards "ok"?',
                               "home.faq_answer_3": "Yes & no"}), tmp_path)
    s = (tmp_path / "index.html").read_text()
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', s, re.S)
    faq = [json.loads(b) for b in blocks if "FAQPage" in b][0]
    assert faq["mainEntity"][2]["name"] == 'Cards "ok"?'
    assert faq["mainEntity"][2]["acceptedAnswer"]["text"] == "Yes & no"
    assert "Cards &quot;ok&quot;?" in s or "Cards \"ok\"?" in s
