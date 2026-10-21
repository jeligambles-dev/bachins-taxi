"""/admin/text: edit the wording of the site, grouped by page."""
from flask import redirect, render_template, request

from content import ValidationError
from texts import all_text_defaults

from . import bp
from .auth import flash_ok, login_required
from .forms import publish, publisher


def _norm(v):
    return v.replace("\r\n", "\n").replace("\r", "\n").rstrip()


def _mutator(form, defaults):
    def mutate(view):
        texts = dict(view.get("texts", {}))
        errors = []
        for key, meta in defaults.items():
            if f"reset__{key}" in form:
                texts.pop(key, None)
                continue
            if f"t__{key}" not in form:
                continue
            value = _norm(form[f"t__{key}"])
            default = meta["default"].rstrip()
            if not value and default:
                errors.append(f"{meta['label']} can't be empty ({meta['group']})")
            elif value == default:
                texts.pop(key, None)
            else:
                texts[key] = value
        if errors:
            raise ValidationError(errors)
        return {"texts": texts}
    return mutate


@bp.route("/text", methods=["GET", "POST"])
@login_required
def texts_page():
    defaults = all_text_defaults()
    errors = []
    if request.method == "POST":
        errors = publish(_mutator(request.form, defaults))
        if not errors:
            flash_ok("Saved. The site is updated.")
            return redirect("/admin/text")
    current = publisher().content().get("texts", {})
    form = request.form if request.method == "POST" else None
    groups, open_groups = {}, set()
    for key, meta in defaults.items():
        live = current.get(key, meta["default"])
        value = form.get(f"t__{key}", live) if form is not None else live
        field = {"key": key, "label": meta["label"], "default": meta["default"],
                 "value": value, "reset": bool(form and f"reset__{key}" in form),
                 "area": meta["multiline"] or len(meta["default"]) > 80
                         or len(value) > 80}
        groups.setdefault(meta["group"], []).append(field)
        if form is not None and (
                (not _norm(value) and meta["default"].rstrip() and not field["reset"])
                or (_norm(value) != _norm(live) and not field["reset"])):
            open_groups.add(meta["group"])
    return render_template("admin/texts.html", groups=groups, open_groups=open_groups,
                           errors=errors)
