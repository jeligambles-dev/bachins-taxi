"""The /admin blueprint. Editor pages are added by later tasks."""
from flask import (Blueprint, abort, current_app, render_template, request, redirect,
                   session)

from . import auth
from .auth import flash_err, flash_ok, login_required  # noqa: F401 (re-exported)

bp = Blueprint("admin", __name__, url_prefix="/admin",
               template_folder="../templates", static_folder="../static",
               static_url_path="/static")

bp.before_request(auth.check_csrf)
bp.add_app_template_global(auth.csrf_token, "csrf_token")


@bp.after_request
def _headers(resp):
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    return resp


@bp.get("/login")
def login_form():
    if session.get("admin"):
        return redirect("/admin/")
    auth.csrf_token()
    return render_template("admin/login.html", next=auth.safe_next(request.args.get("next")))


@bp.post("/login")
def login():
    limiter = current_app.extensions["admin_limiter"]
    ip = request.remote_addr or "?"
    nxt = auth.safe_next(request.form.get("next"))
    if limiter.blocked(ip):
        return render_template("admin/login.html", next=nxt,
                               error="Too many attempts. Try again in 15 minutes."), 429
    if not auth.password_ok(request.form.get("password", ""),
                            current_app.config["ADMIN_PASSWORD"]):
        limiter.fail(ip)
        return render_template("admin/login.html", next=nxt,
                               error="Wrong password."), 200
    limiter.clear(ip)
    session.clear()  # new session: prevents fixation
    session["admin"] = True
    session.permanent = True
    auth.new_csrf()
    return redirect(nxt)


@bp.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    if request.method != "POST":
        abort(405)
    session.clear()
    return redirect("/admin/login")


@bp.get("/")
@login_required
def dashboard():
    flags = current_app.extensions["publisher"].content().get("flags", {})
    return render_template("admin/dashboard.html",
                           email_unconfirmed=bool(flags.get("email_unconfirmed")))
