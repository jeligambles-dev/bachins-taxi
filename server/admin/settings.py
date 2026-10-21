"""/admin/contact: phone, email, WhatsApp, plus the email-confirmation flag."""
import re

from flask import redirect, render_template, request

from content import ValidationError

from . import bp
from .auth import flash_err, flash_ok, login_required
from .forms import publish, publisher

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^\+?[0-9 ]{7,20}$")
_WHATSAPP = re.compile(r"^[0-9]{7,15}$")
FIELDS = ("phone", "phone_display", "email", "whatsapp_number")


def _mutator(form):
    vals = {k: form.get(k, "").strip() for k in FIELDS}

    def mutate(view):
        errors = []
        if not _PHONE.match(vals["phone"]):
            errors.append("Phone number must be 7 to 20 digits or spaces, optionally "
                          "starting with + (e.g. +353 87 033 0046)")
        if not vals["phone_display"]:
            errors.append("Phone number as shown on the site can't be empty")
        if not _EMAIL.match(vals["email"]):
            errors.append("Email address doesn't look right (e.g. name@example.com)")
        if not _WHATSAPP.match(vals["whatsapp_number"]):
            errors.append("WhatsApp number must be digits only, 7 to 15 of them "
                          "(country code, no + or spaces, e.g. 353870330046)")
        if errors:
            raise ValidationError(errors)
        out = {"settings": {**view["settings"], **vals}}
        if vals["email"] != view["settings"].get("email"):
            out["flags"] = {**view.get("flags", {}), "email_unconfirmed": vals["email"]}
        return out
    return mutate


def banner_email(content):
    """The address awaiting confirmation, or None."""
    flag = content.get("flags", {}).get("email_unconfirmed")
    if not flag:
        return None
    return flag if isinstance(flag, str) else content["settings"]["email"]


@bp.route("/contact", methods=["GET", "POST"])
@login_required
def contact():
    errors = []
    if request.method == "POST":
        errors = publish(_mutator(request.form))
        if not errors:
            flash_ok("Saved. The site is updated.")
            return redirect("/admin/contact")
    c = publisher().content()
    src = request.form if request.method == "POST" else c["settings"]
    vals = {k: src.get(k, "") for k in FIELDS}
    return render_template("admin/settings.html", vals=vals, errors=errors,
                           email_unconfirmed=banner_email(c))


@bp.post("/contact/confirm")
@login_required
def contact_confirm():
    errors = publish(lambda v: {"flags": {k: x for k, x in v.get("flags", {}).items()
                                          if k != "email_unconfirmed"}})
    if errors:
        flash_err(errors[0])
    else:
        flash_ok("Thanks. Booking email marked as confirmed.")
    return redirect("/admin/")
