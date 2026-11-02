"""/admin/photos: upload, assign to the homepage slots, view and delete."""
from flask import Response, abort, redirect, render_template, request

from content import ValidationError

from . import bp
from .auth import flash_err, flash_ok, login_required
from .forms import publish, publisher
from server.images import ImageError, process_upload

SLOTS = (("hero", "Homepage hero"), ("taxi", "Taxi photo"), ("logo", "Logo"))
GONE = "This photo was already deleted in another tab or device."
FILE_MAX = 25 * 1024 * 1024
SAVED = "Saved. The site is updated."


def used_by(view, photo_id):
    """Labels of everything using this photo: slots, tours, then vehicles (hidden ones too)."""
    out = [label for slot, label in SLOTS if view["photo_slots"].get(slot) == photo_id]
    out += [t["name"] for t in view["tours"] if t.get("photo") == photo_id]
    out += [f"{v['name']} (vehicle)" for v in view.get("fleet", []) if v.get("photo") == photo_id]
    return out


def _used_text(names):
    return "Used by: " + ", ".join(names)


@bp.get("/photos")
@login_required
def photos_page():
    c = publisher().content()
    metas = publisher().store.list_photos()
    rows = [dict(p, used=used_by(c, p["id"])) for p in metas]
    slots = [(s, label, c["photo_slots"].get(s) or "") for s, label in SLOTS]
    return render_template("admin/photos.html", photos=rows, slots=slots)


@bp.post("/photos")
@login_required
def photos_upload():
    store = publisher().store
    done, skipped = 0, []
    for f in request.files.getlist("files"):
        name = (f.filename or "").strip()
        if not name:
            continue
        name = name.replace("\\", "/").rsplit("/", 1)[-1][:120] or "photo"
        raw = f.read(FILE_MAX + 1)
        if len(raw) > FILE_MAX:
            skipped.append(f"{name}: Photo too big (max 25 MB)")
            continue
        try:
            data, mime, w, h = process_upload(raw)
        except ImageError as e:
            skipped.append(f"{name}: {e}")
            continue
        store.add_photo(data, mime, w, h, name)
        done += 1
    if not done and not skipped:
        flash_err("Choose at least one photo first.")
    else:
        msg = f"{done} uploaded"
        if skipped:
            msg += f", {len(skipped)} skipped: " + "; ".join(skipped)
        (flash_ok if done else flash_err)(msg if skipped else msg + ". Assign them below to put them on the site.")
    return redirect("/admin/photos")


@bp.get("/photos/<photo_id>/raw")
@login_required
def photo_raw(photo_id):
    row = publisher().store.get_photo(photo_id)
    if row is None or row["mime"] not in ("image/jpeg", "image/png"):
        abort(404)
    resp = Response(row["data"], mimetype=row["mime"])
    resp.headers["Cache-Control"] = "private, max-age=3600"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Content-Disposition"] = "inline"
    return resp


@bp.post("/photos/slots")
@login_required
def photos_slots():
    form = request.form

    def mutate(view):
        ids = {p["id"] for p in publisher().store.list_photos()}
        slots = dict(view["photo_slots"])
        errors, changed = [], False
        for slot, label in SLOTS:
            if "slot_" + slot not in form:
                continue
            want = form.get("slot_" + slot, "").strip()
            o = form.get("o__slot_" + slot)
            if o is not None and o == want:
                continue                      # this tab didn't change it
            if want and want not in ids:
                errors.append(f"{label}: that photo doesn't exist any more. Pick another.")
                continue
            if (want or None) != slots.get(slot):
                slots[slot] = want or None
                changed = True
        if errors:
            raise ValidationError(errors)
        return {"photo_slots": slots} if changed else {}
    errors = publish(mutate)
    if errors:
        c = publisher().content()
        rows = [dict(p, used=used_by(c, p["id"])) for p in publisher().store.list_photos()]
        slots = [(s, label, form.get("slot_" + s, "")) for s, label in SLOTS]
        return render_template("admin/photos.html", photos=rows, slots=slots,
                               errors=errors), 200
    flash_ok(SAVED)
    return redirect("/admin/photos")


@bp.route("/photos/<photo_id>/delete", methods=["GET", "POST"])
@login_required
def photo_delete(photo_id):
    store = publisher().store
    errors = []
    if request.method == "POST":
        if not any(p["id"] == photo_id for p in store.list_photos()):
            flash_err(GONE)
            return redirect("/admin/photos")

        def mutate(view):
            if not any(p["id"] == photo_id for p in store.list_photos()):
                raise ValidationError([GONE])
            names = used_by(view, photo_id)
            if names:
                raise ValidationError([_used_text(names)])
            store.delete_photo(photo_id)
            return {}                         # still rebuilds: the file leaves the release
        errors = publish(mutate)
        if not errors:
            flash_ok(SAVED)
            return redirect("/admin/photos")
    meta = next((p for p in store.list_photos() if p["id"] == photo_id), None)
    if meta is None:
        abort(404)
    names = used_by(publisher().content(), photo_id)
    return render_template("admin/photo_delete.html", p=meta, used=names, errors=errors)
