import pytest

from server.app import create_app
from tests.conftest import ADMIN_PASSWORD, csrf_of


def login(client, password=ADMIN_PASSWORD, **extra):
    data = {"password": password, "csrf": csrf_of(client), **extra}
    return client.post("/admin/login", data=data)


def test_admin_redirects_to_login(client):
    r = client.get("/admin/")
    assert r.status_code == 302
    assert r.headers["Location"].startswith("/admin/login?next=")


def test_login_wrong_password(client):
    r = login(client, "nope")
    assert r.status_code == 200
    assert b"Wrong password" in r.data
    assert client.get("/admin/").status_code == 302


def test_login_ok_then_dashboard(client):
    r = login(client)
    assert r.status_code == 302 and r.headers["Location"] == "/admin/"
    d = client.get("/admin/")
    assert d.status_code == 200
    for href in ("/admin/prices", "/admin/tours", "/admin/multi-day",
                 "/admin/photos", "/admin/text", "/admin/contact"):
        assert href.encode() in d.data
    assert d.headers["Cache-Control"] == "no-store"
    assert d.headers["X-Frame-Options"] == "DENY"
    assert d.headers["Referrer-Policy"] == "same-origin"


def test_login_regenerates_session(client):
    before = csrf_of(client)
    login(client)
    assert csrf_of(client) != before


def test_post_without_csrf_400(client):
    assert client.post("/admin/login", data={"password": ADMIN_PASSWORD}).status_code == 400
    csrf_of(client)
    assert client.post("/admin/login", data={"password": ADMIN_PASSWORD,
                                             "csrf": "wrong"}).status_code == 400


def test_logout_post_needs_csrf(logged_in):
    assert logged_in.post("/admin/logout").status_code == 400
    assert logged_in.get("/admin/").status_code == 200


def test_logout_requires_post(logged_in):
    assert logged_in.get("/admin/logout").status_code == 405
    assert logged_in.get("/admin/").status_code == 200
    r = logged_in.post("/admin/logout", data={"csrf": csrf_of(logged_in)})
    assert r.status_code == 302
    assert logged_in.get("/admin/").status_code == 302


def test_rate_limit_after_5_failures(client):
    for _ in range(5):
        assert login(client, "bad").status_code == 200
    r = login(client)  # correct password, but locked out
    assert r.status_code == 429
    assert b"Too many attempts. Try again in 15 minutes." in r.data
    assert client.get("/admin/").status_code == 302


def test_rate_limit_window_expires_and_success_clears(app, client):
    lim = app.extensions["admin_limiter"]
    t = [1000.0]
    lim.clock = lambda: t[0]
    for _ in range(5):
        login(client, "bad")
    assert login(client).status_code == 429
    t[0] += 15 * 60 + 1
    assert login(client, "bad").status_code == 200
    assert login(client).status_code == 302
    client.post("/admin/logout", data={"csrf": csrf_of(client)})
    for _ in range(5):  # counter was cleared by the success
        assert login(client, "bad").status_code == 200


def test_rate_limit_uses_forwarded_client_ip(client):
    for _ in range(5):
        client.post("/admin/login", data={"password": "bad", "csrf": csrf_of(client)},
                    headers={"X-Forwarded-For": "1.1.1.1"})
    r = client.post("/admin/login", data={"password": ADMIN_PASSWORD, "csrf": csrf_of(client)},
                    headers={"X-Forwarded-For": "1.1.1.1"})
    assert r.status_code == 429
    r = client.post("/admin/login", data={"password": ADMIN_PASSWORD, "csrf": csrf_of(client)},
                    headers={"X-Forwarded-For": "2.2.2.2"})
    assert r.status_code == 302


@pytest.mark.parametrize("nxt,expected", [
    ("/admin/prices", "/admin/prices"),
    ("https://evil.example/admin", "/admin/"),
    ("//evil.example/admin", "/admin/"),
    ("/tours", "/admin/"),
    ("/adminx", "/admin/"),
    ("/admin/\\evil", "/admin/"),
    ("/admin/../", "/admin/"),
    ("/admin/..//evil.com", "/admin/"),
    ("/admin//evil.com", "/admin/"),
])
def test_next_only_same_site_admin(client, nxt, expected):
    r = login(client, next=nxt)
    assert r.status_code == 302 and r.headers["Location"] == expected


def test_login_required_preserves_next(client):
    r = client.get("/admin/?x=1")
    assert r.headers["Location"] == "/admin/login?next=/admin/%3Fx%3D1"


def test_cookie_flags(store, tmp_path, monkeypatch):
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    app = create_app(store, tmp_path / "site", admin_password=ADMIN_PASSWORD,
                     secret_key="k", testing=False)
    r = app.test_client().get("/admin/login")
    cookie = r.headers["Set-Cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_session_is_permanent_after_login(client):
    r = login(client)
    assert "Expires=" in r.headers["Set-Cookie"]
    assert client.application.config["PERMANENT_SESSION_LIFETIME"].days == 30
    assert client.application.config["MAX_CONTENT_LENGTH"] == 100 * 1024 * 1024


def test_admin_static_served_and_app_static_not(client):
    r = client.get("/admin/static/admin.css")
    assert r.status_code == 200 and "css" in r.mimetype
    assert client.get("/static/admin.css").status_code == 404
    assert client.get("/admin/static/../app.py").status_code == 404


def test_dashboard_email_banner(app, logged_in):
    assert b"email-unconfirmed" not in logged_in.get("/admin/").data
    pub = app.extensions["publisher"]
    orig = pub.content
    def content():
        c = orig()
        c["flags"] = {**c.get("flags", {}), "email_unconfirmed": True}
        return c
    pub.content = content
    assert b"email-unconfirmed" in logged_in.get("/admin/").data


def test_limiter_atomic_under_parallel_burst(app):
    import threading
    lim = app.extensions["admin_limiter"]
    results = []
    barrier = threading.Barrier(40)

    def hit():
        barrier.wait()
        results.append(lim.attempt("1.2.3.4"))
    ts = [threading.Thread(target=hit) for _ in range(40)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert results.count(False) == 5


def test_password_change_revokes_session(app, logged_in):
    assert logged_in.get("/admin/").status_code == 200
    app.config["ADMIN_PASSWORD"] = "a-different-password"
    r = logged_in.get("/admin/")
    assert r.status_code == 302 and r.headers["Location"].startswith("/admin/login")


def test_forwarded_for_spoof_does_not_evade_limit(client):
    def post(pw, xff):
        return client.post("/admin/login", data={"password": pw, "csrf": csrf_of(client)},
                           headers={"X-Forwarded-For": xff})
    for _ in range(5):
        post("bad", "9.9.9.9, 1.1.1.1")
    assert post(ADMIN_PASSWORD, "8.8.8.8, 1.1.1.1").status_code == 429
