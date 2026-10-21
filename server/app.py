"""Flask app: builds the site from the DB on boot, then serves the live
release. Admin routes are added in later tasks."""
import logging
import os
from pathlib import Path

from flask import Flask, Response, redirect, request, send_file
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import safe_join

from content import resolve_redirect
from server.publish import Publisher
from server.store import Store

log = logging.getLogger("bch.app")

LONG = "public, max-age=604800"
SHORT = "public, max-age=3600"


def _cache_control(rel: str, is_html: bool) -> str:
    if not is_html:
        top = rel.split("/", 1)[0]
        if top in ("images", "uploads"):
            return LONG
        if top in ("css", "js"):
            return SHORT
    return "no-cache"


def create_app(store, site_root, *, admin_password, secret_key, testing=False):
    # Admin static assets (server/static/) are wired up in the admin task.
    app = Flask(__name__, static_folder=None)
    app.config.update(SECRET_KEY=secret_key, TESTING=testing,
                      ADMIN_PASSWORD=admin_password)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    store.migrate()
    publisher = Publisher(store, site_root)
    try:
        publisher.rebuild()
    except Exception:
        # Start anyway so the owner can fix bad data via the admin.
        log.exception("boot rebuild failed; serving previous release if any")
    app.extensions["store"] = store
    app.extensions["publisher"] = publisher

    @app.get("/health")
    def health():
        if publisher.current_dir() is None:
            return Response("unavailable", status=503, mimetype="text/plain")
        return Response("ok", mimetype="text/plain")

    def _send(root, rel, status=200):
        resp = send_file(rel, conditional=(status == 200))
        resp.status_code = status
        is_html = rel.endswith(".html")
        resp.headers["Cache-Control"] = _cache_control(
            str(Path(rel).relative_to(root)), is_html)
        return resp

    def _find(root: Path, path: str):
        for cand in (path, path + ".html", path + "/index.html"):
            full = safe_join(str(root), cand)
            if full and Path(full).is_file():
                return full
        return None

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def public(path):
        if path == "admin" or path.startswith("admin/"):
            return Response("Not found", status=404, mimetype="text/plain")
        root = publisher.current_dir()
        if root is None:
            return Response("unavailable", status=503, mimetype="text/plain")
        path = path.rstrip("/")
        if path == "":
            return _send(root, str(root / "index.html"))
        found = _find(root, path)
        if found:
            return _send(root, found)
        if path.startswith("tours/") and path.count("/") == 1:
            slug = path[len("tours/"):]
            if slug.endswith(".html"):
                slug = slug[:-5]
            new = resolve_redirect(slug, publisher.content().get("redirects", {}))
            if new != slug and (root / "tours" / f"{new}.html").is_file():
                return redirect(f"/tours/{new}.html", code=301)
        index = root / "index.html"
        return _send(root, str(index), status=404)

    return app


def create_app_from_env():
    password = os.environ.get("ADMIN_PASSWORD", "")
    secret = os.environ.get("SECRET_KEY", "")
    if len(password) < 12:
        raise RuntimeError("ADMIN_PASSWORD must be at least 12 characters")
    if not secret:
        raise RuntimeError("SECRET_KEY is required")
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is required")
    return create_app(Store(dsn), Path(os.environ.get("SITE_ROOT", "/tmp/bch-site")),
                      admin_password=password, secret_key=secret)
