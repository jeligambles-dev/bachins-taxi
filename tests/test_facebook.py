"""Facebook page link: footer, Help page, search-engine data, editable in /admin > Contact."""
from pathlib import Path

import build
from content import default_content, merge
from tests.conftest import csrf_of

FB = "https://www.facebook.com/profile.php?id=61563981646974"
FB_ESC = "https://www.facebook.com/profile.php?id=61563981646974"   # no & or quotes to escape


def _build(tmp_path, settings=None):
    c = merge(default_content(), {"settings": {**default_content()["settings"], **(settings or {})}})
    build.build_site(c, tmp_path)
    return tmp_path


def test_default_facebook_link_in_every_footer(tmp_path):
    out = _build(tmp_path)
    for p in Path(out).rglob("*.html"):
        foot = p.read_text()
        foot = foot[foot.index('class="site-footer'):]
        assert f'<a href="{FB_ESC}" target="_blank" rel="noopener">Facebook</a>' in foot, p


def test_facebook_on_help_page_and_in_jsonld(tmp_path):
    out = _build(tmp_path)
    help_h = (out / "help.html").read_text()
    contact = help_h[help_h.index('id="contact"'):]
    assert f'href="{FB_ESC}"' in contact
    home = (out / "index.html").read_text()
    assert f'"sameAs": ["{FB}"]' in home


def test_blank_facebook_hides_link(tmp_path):
    out = _build(tmp_path, {"facebook_url": ""})
    for page in ("index.html", "help.html"):
        h = (out / page).read_text()
        assert "facebook.com" not in h and "sameAs" not in h, page


def _form(**over):
    d = {"phone": "+353 87 033 0046", "phone_display": "087 033 0046",
         "email": "old@example.com", "whatsapp_number": "353870330046"}
    d.update(over)
    return d


def test_admin_contact_edits_facebook(app, logged_in):
    pub = app.extensions["publisher"]
    cur = pub.content()["settings"]
    new = "https://www.facebook.com/bchgroup"
    r = logged_in.post("/admin/contact", data={"csrf": csrf_of(logged_in),
                                               **_form(email=cur["email"], facebook_url=new)})
    assert r.status_code == 302
    assert pub.content()["settings"]["facebook_url"] == new
    assert new in logged_in.get("/index.html").get_data(as_text=True)
    page = logged_in.get("/admin/contact").get_data(as_text=True)
    assert 'name="facebook_url"' in page


def test_admin_contact_rejects_non_facebook_url(app, store, logged_in):
    before = store.load()
    for bad in ("javascript:alert(1)", "http://evil.example/facebook.com", "facebook"):
        r = logged_in.post("/admin/contact", data={"csrf": csrf_of(logged_in), **_form(facebook_url=bad)})
        assert r.status_code == 200 and b"flash err" in r.data, bad
    assert store.load() == before


def test_contact_form_without_facebook_field_keeps_it(app, logged_in):
    pub = app.extensions["publisher"]
    cur = pub.content()["settings"]
    logged_in.post("/admin/contact", data={"csrf": csrf_of(logged_in), **_form(email=cur["email"])})
    assert pub.content()["settings"]["facebook_url"] == FB
