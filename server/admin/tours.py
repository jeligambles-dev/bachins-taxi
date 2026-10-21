"""/admin/tours and /admin/multi-day: add, edit, hide and delete."""
import re

from flask import abort, redirect, render_template, request

from content import (KINDS, ValidationError, blog_links_to, price_label, rename_slug,
                     resolve_redirect, validate_tour, _SLUG_RE)

from . import bp
from .auth import flash_err, flash_ok, login_required
from .forms import digest, parse_int, publish, publisher, too_long

PRICE_MAX = 100000
SINGLE = {"name": 200, "region": 200, "area": 200, "duration": 200, "drive": 200}
MULTI = {"desc": 600, "intro": 4000}
HL_MAX_LINES, HL_LINE_MAX = 12, 200
GONE = "This tour was deleted in another tab or device."
GONE_ROUTE = "This route was deleted in another tab or device."
SAVED = "Saved. The site is updated."
RESERVED = {"new"}


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


# ── tour form values ────────────────────────────────────────────────────────
def shown_values(t):
    """Strings as shown in the edit form for a tour dict."""
    return {"name": t["name"], "slug": t["slug"], "kind": t["kind"],
            "published": "1" if t["published"] else "0",
            "fav": "1" if t["fav"] else "0",
            "price": "" if t["price"] is None else str(t["price"]),
            "photo": t["photo"] or "", "region": t["region"], "area": t["area"],
            "duration": t["duration"], "drive": t["drive"], "desc": t["desc"],
            "intro": t["intro"], "highlights": "\n".join(t["highlights"])}


def _orig_of(field, value):
    if field in MULTI or field == "highlights":
        return digest(_norm(value) if field != "highlights" else "\n".join(_lines(value)))
    return (value or "").strip()


def orig_values(shown):
    return {f: _orig_of(f, v) for f, v in shown.items()}


def _form_values(form):
    v = {f: form.get(f, "") for f in ("name", "slug", "kind", "price", "photo", "region",
                                     "area", "duration", "drive", "desc", "intro",
                                     "highlights")}
    v["published"] = "1" if "published" in form else "0"
    v["fav"] = "1" if "fav" in form else "0"
    return v


def _touched(form, field, value):
    o = form.get("o__" + field)
    return o is None or o != _orig_of(field, value)


def _renamed_to(tours, redirects, slug):
    """The existing tour that `slug` was renamed to, or None."""
    new = resolve_redirect(slug, redirects)
    if new == slug:
        return None
    return next((t for t in tours if t["slug"] == new), None)


def _tour_mutator(form, orig_slug):
    sub = _form_values(form)

    def mutate(view):
        errors = []
        new = orig_slug is None
        touched = {f: new or _touched(form, f, sub[f]) for f in sub}
        if "photo" not in form:       # missing field = untouched; only photo="" clears
            touched["photo"] = False
        # field-level checks on what the user changed
        for f, cap in SINGLE.items():
            if touched[f]:
                e = too_long(sub[f].strip(), f.capitalize(), cap)
                errors += [e] if e else []
        for f, cap in MULTI.items():
            if touched[f]:
                e = too_long(_norm(sub[f]), "Description" if f == "desc" else "Introduction", cap)
                errors += [e] if e else []
        hl = _lines(sub["highlights"])
        if touched["highlights"]:
            if len(hl) > HL_MAX_LINES:
                errors.append(f"Highlights: at most {HL_MAX_LINES} lines (you have {len(hl)})")
            errors += [e for e in (too_long(x, "A highlight line", HL_LINE_MAX) for x in hl) if e]
        price = None
        if touched["price"]:
            price, e = parse_int(sub["price"], "Price", 0, PRICE_MAX, blank_ok=True)
            if e:
                errors.append(e)
        if touched["photo"] and sub["photo"].strip():
            ids = {p["id"] for p in publisher().store.list_photos()}
            if sub["photo"].strip() not in ids:
                errors.append("That photo doesn't exist any more. Pick another.")
        if touched["name"] and not sub["name"].strip():
            errors.append("The tour name cannot be empty.")
        if touched["slug"]:
            e = too_long(sub["slug"].strip(), "Web address", 200)
            errors += [e] if e else []
        if errors:
            raise ValidationError(errors)

        tours = view["tours"]
        redirects = dict(view["redirects"])
        if new:
            slug = sub["slug"].strip().lower()
            if not slug:
                slug = _unique(slugify(sub["name"]), {t["slug"] for t in tours})
                if not slug:
                    raise ValidationError(["Enter a tour name (or a web address)."])
            from content import normalize_tour
            t = normalize_tour({"slug": slug})
            others = tours
            tours = tours + [t]
            redirects.pop(slug, None)
            cur = slug
        else:
            if not any(t["slug"] == orig_slug for t in tours):
                moved = _renamed_to(tours, view["redirects"], orig_slug)
                if moved:
                    raise ValidationError([
                        f"This tour was renamed to {moved['name']} in another tab or "
                        "device. Reload and try again."])
                raise ValidationError([GONE])
            cur = orig_slug
            if touched["slug"]:
                ns = sub["slug"].strip().lower()
                if not ns:
                    raise ValidationError(["The web address can't be empty."])
                if ns in RESERVED:
                    raise ValidationError([f"\"{ns}\" can't be used as a web address."])
                if ns != orig_slug:
                    r = rename_slug({"tours": tours, "redirects": redirects}, orig_slug, ns)
                    tours, redirects, cur = r["tours"], r["redirects"], ns
        t = next(x for x in tours if x["slug"] == cur)
        if new and cur in RESERVED:
            raise ValidationError([f"\"{cur}\" can't be used as a web address."])
        if touched["name"]:
            t["name"] = sub["name"].strip()
        for f in ("kind",):
            if touched[f]:
                t[f] = sub[f]
        for f in ("region", "area", "duration", "drive"):
            if touched[f]:
                t[f] = sub[f].strip()
        for f in MULTI:
            if touched[f]:
                t[f] = _norm(sub[f])
        if touched["highlights"]:
            t["highlights"] = hl
        if touched["price"]:
            t["price"] = price
        if touched["photo"]:
            t["photo"] = sub["photo"].strip() or None
        if touched["published"]:
            t["published"] = sub["published"] == "1"
        if touched["fav"]:
            t["fav"] = sub["fav"] == "1"
        errs = validate_tour(t, [x for x in tours if x is not t])
        if errs:
            raise ValidationError(errs)
        return {"tours": tours, "redirects": redirects}
    return mutate


def _grouped(tours):
    return [(k, label, [t for t in tours if t["kind"] == k]) for k, label in
            (("day", "Day tours"), ("pub", "Rural pub tours"), ("golf", "Golf trips"))]


@bp.get("/tours")
@login_required
def tours_list():
    c = publisher().content()
    rows = [(k, label, [dict(t, price_text=price_label(t)) for t in ts])
            for k, label, ts in _grouped(c["tours"])]
    return render_template("admin/tours_list.html", groups=rows)


def _edit_page(orig_slug, values, orig, errors, kind):
    photos = publisher().store.list_photos()
    cur = (values.get("photo") or "").strip()
    missing = cur if cur and cur not in {p["id"] for p in photos} else None
    return render_template("admin/tour_edit.html", orig_slug=orig_slug, v=values, o=orig,
                           errors=errors, kinds=KINDS, photos=photos, kind=kind,
                           missing_photo=missing)


@bp.route("/tours/new", methods=["GET", "POST"])
@login_required
def tour_new():
    if request.method == "POST":
        errors = publish(_tour_mutator(request.form, None))
        if not errors:
            flash_ok(SAVED)
            return redirect("/admin/tours")
        f = request.form
        return _edit_page(None, _form_values(f), {k: f.get("o__" + k, "") for k in _form_values(f)},
                          errors, f.get("kind"))
    kind = request.args.get("kind")
    kind = kind if kind in KINDS else "day"
    v = {"name": "", "slug": "", "kind": kind, "published": "1", "fav": "0", "price": "",
         "photo": "", "region": "", "area": "", "duration": "", "drive": "", "desc": "",
         "intro": "", "highlights": ""}
    return _edit_page(None, v, orig_values(v), [], kind)


@bp.route("/tours/<slug>", methods=["GET", "POST"])
@login_required
def tour_edit(slug):
    c = publisher().content()
    t = next((x for x in c["tours"] if x["slug"] == slug), None)
    if request.method == "POST":
        errors = publish(_tour_mutator(request.form, slug))
        if not errors:
            flash_ok(SAVED)
            return redirect("/admin/tours")
        f = request.form
        sv = shown_values(t) if t else {}
        orig = {k: f.get("o__" + k, orig_values(sv).get(k, "")) for k in _form_values(f)}
        return _edit_page(slug, _form_values(f), orig, errors, f.get("kind"))
    if t is None:
        moved = _renamed_to(c["tours"], c["redirects"], slug)
        if moved:
            return redirect(f"/admin/tours/{moved['slug']}")
        abort(404)
    v = shown_values(t)
    return _edit_page(slug, v, orig_values(v), [], t["kind"])


@bp.post("/tours/<slug>/publish")
@login_required
def tour_publish(slug):
    want = request.form.get("published") == "1"

    def mutate(view):
        t = next((x for x in view["tours"] if x["slug"] == slug), None)
        if t is None:
            raise ValidationError([GONE])
        t["published"] = want
        return {"tours": view["tours"]}
    errors = publish(mutate)
    if errors:
        flash_err(" ".join(errors))
    else:
        flash_ok(SAVED)
    return redirect("/admin/tours")


@bp.route("/tours/<slug>/delete", methods=["GET", "POST"])
@login_required
def tour_delete(slug):
    c = publisher().content()
    t = next((x for x in c["tours"] if x["slug"] == slug), None)
    errors = []
    if request.method == "POST":
        def mutate(view):
            if not any(x["slug"] == slug for x in view["tours"]):
                raise ValidationError([GONE])
            posts = blog_links_to(slug, view["redirects"])
            if posts:
                raise ValidationError([
                    "Can't delete: these blog posts link to this tour: "
                    + ", ".join(posts) + ". Hide it instead."])
            return {"tours": [x for x in view["tours"] if x["slug"] != slug],
                    "redirects": {k: v for k, v in view["redirects"].items() if v != slug}}
        errors = publish(mutate)
        if not errors:
            flash_ok(SAVED)
            return redirect("/admin/tours")
        c = publisher().content()
        t = next((x for x in c["tours"] if x["slug"] == slug), None)
    if t is None and not errors:
        abort(404)
    posts = blog_links_to(slug, c["redirects"]) if t else []
    return render_template("admin/confirm_delete.html", item=t, slug=slug, posts=posts,
                           errors=errors, what="tour", base="/admin/tours",
                           hide_url=f"/admin/tours/{slug}/publish")


# ── multi-day ───────────────────────────────────────────────────────────────
def multi_shown(m):
    return {"name": m["name"], "slug": m["slug"], "days": str(m["days"]),
            "summary": m["summary"], "plan": "\n".join(m["plan"])}


def _multi_orig(field, value):
    if field in ("summary", "plan"):
        return digest("\n".join(_lines(value)) if field == "plan" else _norm(value))
    return (value or "").strip()


def multi_orig_values(shown):
    return {f: _multi_orig(f, v) for f, v in shown.items()}


def _multi_form(form):
    return {f: form.get(f, "") for f in ("name", "slug", "days", "summary", "plan")}


def _multi_mutator(form, orig_slug):
    sub = _multi_form(form)

    def mutate(view):
        new = orig_slug is None
        touched = {f: new or form.get("o__" + f) is None
                   or form.get("o__" + f) != _multi_orig(f, sub[f]) for f in sub}
        routes = view["multi_day"]
        errors = []
        if new:
            m = {"slug": "", "name": "", "days": 1, "summary": "", "plan": []}
            routes = routes + [m]
        else:
            m = next((x for x in routes if x["slug"] == orig_slug), None)
            if m is None:
                raise ValidationError([GONE_ROUTE])
        others = [x for x in routes if x is not m]
        if touched["name"]:
            name = sub["name"].strip()
            if not name:
                errors.append("The route name cannot be empty.")
            errors += [e for e in [too_long(name, "Name", 200)] if e]
            m["name"] = name
        if touched["slug"]:
            slug = sub["slug"].strip().lower()
            if not slug and new:
                slug = _unique(slugify(sub["name"]), {x["slug"] for x in others})
            if len(slug) > 200:
                errors.append(too_long(slug, "Web address", 200))
            elif not slug or not _SLUG_RE.match(slug) or slug in RESERVED:
                errors.append("The web address (slug) must use only lowercase letters, "
                              "numbers and single hyphens, e.g. my-route.")
            elif any(x["slug"] == slug for x in others):
                errors.append(f"Another route already uses the web address \"{slug}\".")
            m["slug"] = slug
        if touched["days"]:
            d, e = parse_int(sub["days"], "Days", 1, 21, money=False)
            if e:
                errors.append(e)
            else:
                m["days"] = d
        if touched["summary"]:
            s = _norm(sub["summary"])
            errors += [e for e in [too_long(s, "Summary", 600)] if e]
            m["summary"] = s
        if touched["plan"]:
            m["plan"] = _lines(sub["plan"])
            errors += [e for e in (too_long(x, "A day description", 600) for x in m["plan"]) if e]
        if not errors and len(m["plan"]) != m["days"]:
            d, n = m["days"], len(m["plan"])
            errors.append(f"You have {d} day{'' if d == 1 else 's'} but {n} day "
                          f"description{'' if n == 1 else 's'}")
        if errors:
            raise ValidationError(errors)
        return {"multi_day": routes}
    return mutate


@bp.get("/multi-day")
@login_required
def multi_list():
    return render_template("admin/multi_list.html", routes=publisher().content()["multi_day"])


def _multi_page(orig_slug, values, orig, errors):
    return render_template("admin/multi_edit.html", orig_slug=orig_slug, v=values, o=orig,
                           errors=errors)


@bp.route("/multi-day/new", methods=["GET", "POST"])
@login_required
def multi_new():
    if request.method == "POST":
        errors = publish(_multi_mutator(request.form, None))
        if not errors:
            flash_ok(SAVED)
            return redirect("/admin/multi-day")
        f = request.form
        return _multi_page(None, _multi_form(f), {k: f.get("o__" + k, "") for k in _multi_form(f)}, errors)
    v = {"name": "", "slug": "", "days": "2", "summary": "", "plan": ""}
    return _multi_page(None, v, multi_orig_values(v), [])


@bp.route("/multi-day/<slug>", methods=["GET", "POST"])
@login_required
def multi_edit(slug):
    c = publisher().content()
    m = next((x for x in c["multi_day"] if x["slug"] == slug), None)
    if request.method == "POST":
        errors = publish(_multi_mutator(request.form, slug))
        if not errors:
            flash_ok(SAVED)
            return redirect("/admin/multi-day")
        f = request.form
        base = multi_orig_values(multi_shown(m)) if m else {}
        return _multi_page(slug, _multi_form(f),
                           {k: f.get("o__" + k, base.get(k, "")) for k in _multi_form(f)}, errors)
    if m is None:
        abort(404)
    v = multi_shown(m)
    return _multi_page(slug, v, multi_orig_values(v), [])


@bp.route("/multi-day/<slug>/delete", methods=["GET", "POST"])
@login_required
def multi_delete(slug):
    c = publisher().content()
    m = next((x for x in c["multi_day"] if x["slug"] == slug), None)
    errors = []
    if request.method == "POST":
        def mutate(view):
            if not any(x["slug"] == slug for x in view["multi_day"]):
                raise ValidationError([GONE_ROUTE])
            return {"multi_day": [x for x in view["multi_day"] if x["slug"] != slug]}
        errors = publish(mutate)
        if not errors:
            flash_ok(SAVED)
            return redirect("/admin/multi-day")
    if m is None and not errors:
        abort(404)
    return render_template("admin/confirm_delete.html", item=m, slug=slug, posts=[],
                           errors=errors, what="route", base="/admin/multi-day", hide_url=None)
