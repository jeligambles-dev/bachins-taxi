"""Regression tests for the final whole-branch review (one fix wave)."""
import hashlib
import re
import subprocess
from pathlib import Path

import pytest

import build
from content import default_content, merge
from tests.conftest import ADMIN_PASSWORD, csrf_of
from tests.test_admin_forms import base_prices, contact_form, post, _form_of

ROOT = Path(__file__).resolve().parent.parent


def _built(tmp_path, **stored):
    build.build_site(merge(default_content(), stored), tmp_path)
    return tmp_path


def _texts(root):
    return {p.relative_to(root).as_posix(): p.read_text()
            for p in Path(root).rglob("*") if p.suffix in (".html", ".js", ".xml")}


# 1 ── no airport fares ────────────────────────────────────────────────────────

def test_no_airport_fares_builds(tmp_path):
    _built(tmp_path, airport_fares=[])
    assert "€None" not in (tmp_path / "index.html").read_text()


def test_removing_every_fare_is_rejected(app, store, logged_in):
    n = len(app.extensions["publisher"].content()["airport_fares"])
    d = base_prices(app, **{f"fare-{i}-remove": "on" for i in range(n)})
    before = store.load()
    r = post(logged_in, "/admin/prices", d)
    assert r.status_code == 200 and b"at least one airport fare" in r.data
    assert store.load() == before


def test_unexpected_exception_is_friendly(app, store, logged_in, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret detail")
    monkeypatch.setattr("server.publish.build_site", boom)
    before = store.load()
    r = post(logged_in, "/admin/prices", base_prices(app, multi_day_rate="700"))
    assert r.status_code == 200
    assert b"Couldn&#39;t publish" in r.data and b"Nothing was changed." in r.data
    assert b"secret detail" not in r.data
    assert store.load() == before


# 2 ── fare distance escaped ──────────────────────────────────────────────────

def test_fare_distance_is_escaped(tmp_path):
    fares = default_content()["airport_fares"]
    fares[0] = dict(fares[0], distance="<b>5 km</b>")
    _built(tmp_path, airport_fares=fares)
    page = (tmp_path / "index.html").read_text()
    assert "<b>5 km</b>" not in page and "&lt;b&gt;5 km&lt;/b&gt;" in page


# 3 ── contact stale tab ──────────────────────────────────────────────────────

def test_contact_stale_tab_keeps_newer_phone(app, logged_in):
    stale = _form_of(logged_in, "/admin/contact")
    assert post(logged_in, "/admin/contact", {**stale, "phone_display": "087 111 2222"}
                ).status_code == 302
    stale["email"] = "stale@example.com"
    assert post(logged_in, "/admin/contact", stale).status_code == 302
    s = app.extensions["publisher"].content()["settings"]
    assert s["phone_display"] == "087 111 2222" and s["email"] == "stale@example.com"


# 4 ── max passengers threaded through ────────────────────────────────────────

def test_max_passengers_threaded(tmp_path):
    _built(tmp_path, settings={"max_passengers": 6})
    bad = []
    for rel, text in _texts(tmp_path).items():
        text = re.sub(r"8[- ]seater|8 Seater", "", text, flags=re.I)
        for pat in (r"[Uu]p to 8\b(?! seats)", r'max="8"', r"[Mm]ore than 8\b",
                    r"MAX_PAX = 8", r"or 8\b", r"\(9\+\)", r"%289%2B", r"\b9%2B"):
            if re.search(pat, text):
                bad.append((rel, pat))
    assert not bad, bad[:10]
    assert '"maxPax": 6' in (tmp_path / "js" / "config.js").read_text()
    assert "Up to 6" in (tmp_path / "tours" / "ring-of-kerry.html").read_text()
    assert 'max="6"' in (tmp_path / "index.html").read_text()


def test_max_passengers_default_unchanged(tmp_path):
    _built(tmp_path)
    t = (tmp_path / "tours" / "ring-of-kerry.html").read_text()
    assert "Up to 8 passengers" in t and "up to 8 people" in t
    assert 'max="8"' in (tmp_path / "index.html").read_text()


def test_main_js_reads_max_pax_from_config():
    js = (ROOT / "js" / "main.js").read_text()
    assert "MAX_PAX = 8;" not in js and "CFG.maxPax" in js


# 5 ── multi photo upload limits ──────────────────────────────────────────────

def test_request_limit_100mb(app):
    assert app.config["MAX_CONTENT_LENGTH"] == 100 * 1024 * 1024


def test_oversize_single_file_skipped_with_reason(app, logged_in):
    import io
    big = (io.BytesIO(b"0" * (26 * 1024 * 1024)), "big.jpg")
    r = logged_in.post("/admin/photos", data={"csrf": csrf_of(logged_in), "files": [big]},
                       content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    assert b"big.jpg" in r.data and b"max 25 MB" in r.data
    assert app.extensions["publisher"].store.list_photos() == []


def test_413_message_reworded(app, logged_in):
    app.config["MAX_CONTENT_LENGTH"] = 2000
    r = logged_in.post("/admin/photos", data={"csrf": csrf_of(logged_in), "x": "y" * 5000})
    assert r.status_code == 413
    assert "Too much at once (max 100 MB per upload)" in r.get_data(as_text=True)


# 6 ── default footer ─────────────────────────────────────────────────────────

def test_default_footer_matches_original(tmp_path):
    _built(tmp_path)
    page = (tmp_path / "tours.html").read_text()
    foot = page[page.index('<h4>Popular Tours</h4>'):]
    foot = foot[:foot.index("</ul>")]
    assert re.findall(r"tours/([a-z0-9-]+)\.html", foot) == [
        "giants-causeway", "ring-of-kerry", "cliffs-of-moher",
        "glendalough-wicklow", "connemara-galway", "dingle-peninsula"]


# 7 ── session fingerprint ────────────────────────────────────────────────────

def test_session_fingerprint_not_plain_hash(logged_in):
    with logged_in.session_transaction() as s:
        pw = s["pw"]
    assert pw != hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()[:16]
    assert len(pw) == 32


# 8 ── cache-busted assets ────────────────────────────────────────────────────

def test_assets_versioned(tmp_path):
    _built(tmp_path)
    for rel, asset in (("index.html", "js/main.js"), ("index.html", "css/style.css"),
                       ("price-calculator.html", "js/calculator.js"),
                       ("tours.html", "css/pages.css")):
        v = hashlib.sha256((ROOT / asset).read_bytes()).hexdigest()[:8]
        assert f'{asset}?v={v}"' in (tmp_path / rel).read_text(), (rel, asset)


# 9 ── modal price format ─────────────────────────────────────────────────────

def test_modal_price_has_thousands_separator():
    js = (ROOT / "js" / "main.js").read_text()
    assert "'€' + tour.price" not in js and "'€' + currentTour.price" not in js
    assert "toLocaleString" in js


# 10 ── unauthenticated POST rejected before parsing the body ─────────────────

def test_unauth_post_rejected_before_form_parse(client, monkeypatch):
    from flask import Request

    def boom(self, *a, **k):
        raise AssertionError("form parsed before auth")
    monkeypatch.setattr(Request, "_load_form_data", boom)
    r = client.post("/admin/prices", data={"x": "1"})
    assert r.status_code in (302, 403)


def test_login_post_still_csrf_checked(client):
    assert client.post("/admin/login", data={"password": ADMIN_PASSWORD}).status_code == 400


# 11 ── concise unknown-token error ───────────────────────────────────────────

def test_leftover_token_error_is_concise(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "_MODAL_RAW", build._MODAL_RAW + "{{FOO}}")
    with pytest.raises(build.BuildError) as ei:
        _built(tmp_path)
    assert len(ei.value.broken) == 1
    assert "Unknown placeholder {{FOO}}" in ei.value.broken[0]
    assert len(str(ei.value)) < 200
