"""Admin auth: login_required, CSRF, rate limit, flash helpers."""
import hashlib
import hmac
import secrets
import threading
import time
from functools import wraps
from urllib.parse import quote

from flask import abort, current_app, flash, g, redirect, request, session, url_for

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

    def attempt(self, key):
        """Atomically: True if `key` is blocked, else record an attempt and
        return False. Success should call clear()."""
        with self._lock:
            recent = self._recent(key)
            if len(recent) >= MAX_FAILURES:
                return True
            recent.append(self.clock())
            self._fails[key] = recent
            return False

    def clear(self, key):
        with self._lock:
            self._fails.pop(key, None)

    def reset(self):
        with self._lock:
            self._fails.clear()


def pw_fingerprint(password):
    """Keyed, so the readable session cookie never exposes a bare password hash."""
    return hmac.new(current_app.config["SECRET_KEY"].encode(), password.encode(),
                    hashlib.sha256).hexdigest()[:32]


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
    """before_request: every unsafe method under /admin needs a matching token.
    Anonymous requests (except the login POST) are turned away before the body
    is parsed."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if request.path != "/admin/login" and not session.get("admin"):
        return redirect("/admin/login")
    expected = session.get("csrf")
    given = request.form.get("csrf", "")
    if not expected or not hmac.compare_digest(expected.encode(), given.encode()):
        abort(400, "Invalid or missing CSRF token. Reload the page and try again.")


def safe_next(value):
    """Only same-site /admin paths; anything else falls back to the dashboard."""
    if (value and (value == "/admin" or value.startswith("/admin/"))
            and "\\" not in value and "//" not in value
            and ".." not in value.split("?")[0].split("/")
            and all(ch >= " " and ch != "\x7f" for ch in value)):
        return value
    return "/admin/"


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("admin") and session.get("pw") != pw_fingerprint(
                current_app.config["ADMIN_PASSWORD"]):
            session.clear()  # password changed: revoke old sessions
        if not session.get("admin"):
            target = request.full_path if request.query_string else request.path
            return redirect("/admin/login?next=" + quote(target, safe="/"))
        return view(*args, **kwargs)
    return wrapped


def flash_ok(msg):
    flash(msg, "ok")


def flash_err(msg):
    flash(msg, "err")
