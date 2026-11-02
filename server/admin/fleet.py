"""/admin/fleet: add, edit, hide and delete vehicles."""
import re

from flask import abort, redirect, render_template, request

from content import (BAGS_RANGE, FEATURES_MAX, PAX_RANGE, VEHICLE_CAPS, ValidationError,
                     normalize_vehicle, validate_vehicle)

from . import bp
from .auth import flash_err, flash_ok, login_required
from .forms import digest, parse_int, publish, publisher, too_long

GONE = "This vehicle was deleted in another tab or device."
SAVED = "Saved. The site is updated."
RESERVED = {"new"}
FIELDS = ("name", "example", "passengers", "bags", "features", "photo", "price_note", "desc")
LABELS = {"name": "Name", "example": "Example", "price_note": "Price note", "desc": "Description"}


def _norm(v):
    return (v or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _lines(v):
    return [ln.strip() for ln in _norm(v).split("\n") if ln.strip()]


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:80].strip("-")


def _unique(base, taken):
    taken = set(taken) | RESERVED
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def shown_values(v):
    """Strings as shown in the edit form for a vehicle dict."""
    return {"name": v["name"], "slug": v["slug"], "example": v["example"],
            "passengers": str(v["passengers"]), "bags": str(v["bags"]),
            "features": "\n".join(v["features"]), "photo": v["photo"] or "",
            "price_note": v["price_note"], "desc": v["desc"],
            "published": "1" if v["published"] else "0"}


def _orig_of(field, value):
    if field == "desc":
        return digest(_norm(value))
    if field == "features":
        return digest("\n".join(_lines(value)))
    return (value or "").strip()


def orig_values(shown):
    return {f: _orig_of(f, v) for f, v in shown.items()}


def _form_values(form):
    v = {f: form.get(f, "") for f in FIELDS + ("slug",)}
    v["published"] = "1" if "published" in form else "0"
    return v


def _touched(form, field, value):
    o = form.get("o__" + field)
    return o is None or o != _orig_of(field, value)


def _mutator(form, orig_slug):
    sub = _form_values(form)

    def mutate(view):
        errors = []
        new = orig_slug is None
        touched = {f: new or _touched(form, f, sub[f]) for f in sub}
        if "photo" not in form:       # missing field = untouched; only photo="" clears
            touched["photo"] = False
        for f in ("name", "example", "price_note"):
            if touched[f]:
                e = too_long(sub[f].strip(), LABELS[f], VEHICLE_CAPS[f])
                errors += [e] if e else []
        if touched["desc"]:
            e = too_long(_norm(sub["desc"]), "Description", VEHICLE_CAPS["desc"])
            errors += [e] if e else []
        feats = _lines(sub["features"])
        if touched["features"]:
            if len(feats) > FEATURES_MAX:
                errors.append(f"Features: at most {FEATURES_MAX} lines (you have {len(feats)})")
            errors += [e for e in (too_long(x, "A feature line", VEHICLE_CAPS["feature"])
                                   for x in feats) if e]
        pax = bags = None
        if touched["passengers"]:
            pax, e = parse_int(sub["passengers"], "Passengers", *PAX_RANGE, money=False)
            errors += [e] if e else []
        if touched["bags"]:
            bags, e = parse_int(sub["bags"], "Bags", *BAGS_RANGE, money=False)
            errors += [e] if e else []
        if touched["photo"] and sub["photo"].strip():
            ids = {p["id"] for p in publisher().store.list_photos()}
            if sub["photo"].strip() not in ids:
                errors.append("That photo doesn't exist any more. Pick another.")
        if touched["name"] and not sub["name"].strip():
            errors.append("The vehicle name cannot be empty.")
        if new:
            e = too_long(sub["slug"].strip(), "Web address", 200)
            errors += [e] if e else []
        if errors:
            raise ValidationError(errors)

        fleet = view["fleet"]
        if new:
            slug = sub["slug"].strip().lower()
            if not slug:
                slug = _unique(slugify(sub["name"]), {x["slug"] for x in fleet})
                if not slug:
                    raise ValidationError(["Enter a vehicle name (or a web address)."])
            if slug in RESERVED:
                raise ValidationError([f"\"{slug}\" can't be used as a web address."])
            v = normalize_vehicle({"slug": slug})
            fleet = fleet + [v]
        else:
            v = next((x for x in fleet if x["slug"] == orig_slug), None)
            if v is None:
                raise ValidationError([GONE])
        if touched["name"]:
            v["name"] = sub["name"].strip()
        for f in ("example", "price_note"):
            if touched[f]:
                v[f] = sub[f].strip()
        if touched["desc"]:
            v["desc"] = _norm(sub["desc"])
        if touched["features"]:
            v["features"] = feats
        if touched["passengers"]:
            v["passengers"] = pax
        if touched["bags"]:
            v["bags"] = bags
        if touched["photo"]:
            v["photo"] = sub["photo"].strip() or None
        if touched["published"]:
            v["published"] = sub["published"] == "1"
        errs = validate_vehicle(v, [x for x in fleet if x is not v])
        if errs:
            raise ValidationError(errs)
        return {"fleet": fleet}
    return mutate


@bp.get("/fleet")
@login_required
def fleet_list():
    return render_template("admin/fleet_list.html", vehicles=publisher().content()["fleet"])


def _edit_page(orig_slug, values, orig, errors):
    photos = publisher().store.list_photos()
    cur = (values.get("photo") or "").strip()
    missing = cur if cur and cur not in {p["id"] for p in photos} else None
    return render_template("admin/fleet_edit.html", orig_slug=orig_slug, v=values, o=orig,
                           errors=errors, photos=photos, missing_photo=missing)


@bp.route("/fleet/new", methods=["GET", "POST"])
@login_required
def fleet_new():
    if request.method == "POST":
        errors = publish(_mutator(request.form, None))
        if not errors:
            flash_ok(SAVED)
            return redirect("/admin/fleet")
        f = request.form
        return _edit_page(None, _form_values(f), {k: f.get("o__" + k, "") for k in _form_values(f)},
                          errors)
    v = {"name": "", "slug": "", "example": "", "passengers": "4", "bags": "2",
         "features": "", "photo": "", "price_note": "", "desc": "", "published": "1"}
    return _edit_page(None, v, orig_values(v), [])


@bp.route("/fleet/<slug>", methods=["GET", "POST"])
@login_required
def fleet_edit(slug):
    v = next((x for x in publisher().content()["fleet"] if x["slug"] == slug), None)
    if request.method == "POST":
        errors = publish(_mutator(request.form, slug))
        if not errors:
            flash_ok(SAVED)
            return redirect("/admin/fleet")
        f = request.form
        base = orig_values(shown_values(v)) if v else {}
        return _edit_page(slug, _form_values(f),
                          {k: f.get("o__" + k, base.get(k, "")) for k in _form_values(f)}, errors)
    if v is None:
        abort(404)
    sv = shown_values(v)
    return _edit_page(slug, sv, orig_values(sv), [])


@bp.post("/fleet/<slug>/publish")
@login_required
def fleet_publish(slug):
    want = request.form.get("published") == "1"

    def mutate(view):
        v = next((x for x in view["fleet"] if x["slug"] == slug), None)
        if v is None:
            raise ValidationError([GONE])
        v["published"] = want
        return {"fleet": view["fleet"]}
    errors = publish(mutate)
    if errors:
        flash_err(" ".join(errors))
    else:
        flash_ok(SAVED)
    return redirect("/admin/fleet")


@bp.route("/fleet/<slug>/delete", methods=["GET", "POST"])
@login_required
def fleet_delete(slug):
    c = publisher().content()
    v = next((x for x in c["fleet"] if x["slug"] == slug), None)
    errors = []
    if request.method == "POST":
        def mutate(view):
            if not any(x["slug"] == slug for x in view["fleet"]):
                raise ValidationError([GONE])
            return {"fleet": [x for x in view["fleet"] if x["slug"] != slug]}
        errors = publish(mutate)
        if not errors:
            flash_ok(SAVED)
            return redirect("/admin/fleet")
    if v is None and not errors:
        abort(404)
    return render_template("admin/confirm_delete.html", item=v, slug=slug, posts=[],
                           errors=errors, what="vehicle", base="/admin/fleet", hide_url=None)
