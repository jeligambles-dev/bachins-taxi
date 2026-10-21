import pytest

import build
from server.app import create_app, create_app_from_env


@pytest.fixture
def app(store, tmp_path):
    return create_app(store, tmp_path / "site", admin_password="x" * 12,
                      secret_key="k", testing=True)


@pytest.fixture
def client(app):
    return app.test_client()


def test_home_and_pretty_urls(client):
    for p in ("/", "/tours/ring-of-kerry", "/tours/ring-of-kerry.html", "/tours.html"):
        assert client.get(p).status_code == 200, p


def test_unknown_is_404_with_home(client):
    r = client.get("/nope/nothing")
    assert r.status_code == 404
    assert r.data == client.get("/").data


def test_directory_without_index_is_404(client):
    assert client.get("/css").status_code == 404
    assert client.get("/css/").status_code == 404


def test_traversal_blocked(client, app):
    root = app.extensions["publisher"].site_root
    (root / "secret.txt").write_text("SENTINEL-XYZ")
    (root / "releases" / "secret.txt").write_text("SENTINEL-XYZ")
    for p in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt",
              "/../releases/secret.txt", "/%2e%2e/%2e%2e/secret.txt",
              "/releases/secret.txt", "/current/../secret.txt"):
        r = client.get(p)
        assert r.status_code == 404, p
        assert b"SENTINEL-XYZ" not in r.data, p
    r = client.get("//etc/passwd")
    assert r.status_code == 404 and b"root:" not in r.data


def test_cache_headers(client, app):
    cur = app.extensions["publisher"].current_dir()
    css = next((cur / "css").iterdir()).name
    js = next((cur / "js").iterdir()).name
    img = next((cur / "images").iterdir()).name
    assert client.get(f"/css/{css}").headers["Cache-Control"] == "public, max-age=3600"
    assert client.get(f"/js/{js}").headers["Cache-Control"] == "public, max-age=3600"
    assert client.get(f"/images/{img}").headers["Cache-Control"] == "public, max-age=604800"
    assert client.get("/").headers["Cache-Control"] == "no-cache"
    assert client.get("/tours.html").headers["Cache-Control"] == "no-cache"
    assert client.get("/nope").headers["Cache-Control"] == "no-cache"


def test_uploads_cache_header(store, tmp_path):
    p = store.add_photo(b"\xff\xd8\xffAAAA", "image/jpeg", 10, 10, "a.jpg")
    app = create_app(store, tmp_path / "s", admin_password="x" * 12, secret_key="k", testing=True)
    app.extensions["publisher"].apply(lambda v: {"photo_slots": {**v["photo_slots"], "hero": p["id"]}})
    r = app.test_client().get(f"/uploads/{p['sha'][:12]}.jpg")
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "public, max-age=604800"


def test_slug_redirect(store, client, app):
    app.extensions["publisher"].apply(lambda v: {"redirects": {"old": "ring-of-kerry"}})
    for p in ("/tours/old.html", "/tours/old"):
        r = client.get(p)
        assert r.status_code == 301, p
        assert r.headers["Location"] == "/tours/ring-of-kerry.html"


def test_redirect_ignored_when_live_page_exists(client, app):
    app.extensions["publisher"].apply(lambda v: {"redirects": {"ring-of-kerry": "dingle-peninsula"}})
    assert client.get("/tours/ring-of-kerry.html").status_code == 200


def test_boot_builds_from_db_before_healthy(store, tmp_path):
    store.save_sections({"settings": {"email": "boot@x.ie"}})
    app = create_app(store, tmp_path / "fresh", admin_password="x" * 12,
                     secret_key="k", testing=True)
    c = app.test_client()
    assert c.get("/health").status_code == 200
    assert b"boot@x.ie" in c.get("/js/config.js").data
    assert app.extensions["store"] is store


def test_boot_failure_still_starts_health_503(store, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise build.BuildError(["bad data"])
    monkeypatch.setattr("server.publish.build_site", boom)
    app = create_app(store, tmp_path / "fresh", admin_password="x" * 12,
                     secret_key="k", testing=True)
    assert app.test_client().get("/health").status_code == 503


def test_boot_failure_keeps_serving_previous_release(store, tmp_path, monkeypatch):
    site = tmp_path / "site"
    create_app(store, site, admin_password="x" * 12, secret_key="k", testing=True)

    def boom(*a, **k):
        raise build.BuildError(["bad data"])
    monkeypatch.setattr("server.publish.build_site", boom)
    c = create_app(store, site, admin_password="x" * 12, secret_key="k",
                   testing=True).test_client()
    assert c.get("/health").status_code == 200
    assert c.get("/").status_code == 200


def test_admin_paths_not_public(client):
    assert client.get("/admin").status_code == 404
    assert client.get("/admin/x").status_code == 404


def test_env_guard(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql:///x")
    monkeypatch.setenv("ADMIN_PASSWORD", "short")
    monkeypatch.setenv("SECRET_KEY", "k")
    with pytest.raises(RuntimeError):
        create_app_from_env()
    monkeypatch.setenv("ADMIN_PASSWORD", "long-enough-pw")
    monkeypatch.delenv("SECRET_KEY")
    with pytest.raises(RuntimeError):
        create_app_from_env()


def test_weird_paths(client):
    home = client.get("/").data
    for p in ("/%00", "//etc/passwd", "/tours/%2e%2e/x", "/index.html/x"):
        r = client.get(p)
        assert r.status_code == 404, p
        assert r.data == home, p


def test_redirect_cycle_no_loop(client, app):
    app.extensions["publisher"].apply(lambda v: {"redirects": {"a": "b", "b": "a"}})
    r = client.get("/tours/a.html")
    assert r.status_code == 404
    assert "Location" not in r.headers


def test_redirect_to_missing_target_is_404(client, app):
    app.extensions["publisher"].apply(lambda v: {"redirects": {"old": "gone"}})
    assert client.get("/tours/old.html").status_code == 404
