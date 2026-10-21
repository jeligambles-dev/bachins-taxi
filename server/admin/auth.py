"""Admin auth: login_required, CSRF, rate limit, flash helpers."""
import hashlib
import hmac
import secrets
import threading
import time
from functools import wraps
from urllib.parse import quote

from flask import abort, flash, g, redirect, request, session, url_for

MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60


class LoginLimiter:
    """In-memory failed-login counter per client IP (single gunicorn worker
    assumed; with several workers the limit is per worker)."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self._lock = threading.Lock()
        self._fails = {}

    def _recent(self, key):
        cutoff = self.clock() - WINDOW_SECONDS
        recent = [t for t in self._fails.get(key, ()) if t > cutoff]
        if recent:
            self._fails[key] = recent
        else:
            self._fails.pop(key, None)
        return recent

    def blocked(self, key):
        with self._lock:
            return len(self._recent(key)) >= MAX_FAILURES

    def fail(self, key):
        with self._lock:
            recent = self._recent(key)
            recent.append(self.clock())
            self._fails[key] = recent

    def clear(self, key):
        with self._lock:
            self._fails.pop(key, None)

    def reset(self):
        with self._lock:
            self._fails.clear()


def password_ok(given, expected):
    a = hashlib.sha256(given.encode()).digest()
    b = hashlib.sha256(expected.encode()).digest()
    return hmac.compare_digest(a, b)


def new_csrf():
    session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def csrf_token():
    return session.get("csrf") or new_csrf()


def check_csrf():
    """before_request: every unsafe method under /admin needs a matching token."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    expected = session.get("csrf")
    given = request.form.get("csrf", "")
    if not expected or not hmac.compare_digest(expected.encode(), given.encode()):
        abort(400, "Invalid or missing CSRF token. Reload the page and try again.")


def safe_next(value):
    """Only same-site /admin paths; anything else falls back to the dashboard."""
    if (value and (value == "/admin" or value.startswith("/admin/"))
            and "\\" not in value and not value.startswith("//")
            and all(ch >= " " and ch != "\x7f" for ch in value)):
        return value
    return "/admin/"


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            target = request.full_path if request.query_string else request.path
            return redirect("/admin/login?next=" + quote(target, safe="/"))
        return view(*args, **kwargs)
    return wrapped


def flash_ok(msg):
    flash(msg, "ok")


def flash_err(msg):
    flash(msg, "err")
