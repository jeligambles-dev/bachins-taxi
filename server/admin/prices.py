"""/admin/prices: tour prices, rates, airport fares, long transfers."""
from flask import redirect, render_template, request

from content import KINDS, ValidationError

from . import bp
from .auth import flash_ok, login_required
from .forms import indices, parse_int, publish, publisher

PRICE_MAX = 100000
BLANK_ROWS = 2


def _rows_from_content(c):
    fares = [{"area": f["area"], "distance": f.get("distance") or "",
              "to": str(f["to"]), "from": str(f["from"]), "remove": False}
             for f in c["airport_fares"]]
    longs = [{"area": f["area"], "price": str(f["price"]), "remove": False}
             for f in c["long_transfers"]]
    blank_f = {"area": "", "distance": "", "to": "", "from": "", "remove": False}
    blank_l = {"area": "", "price": "", "remove": False}
    return fares + [dict(blank_f) for _ in range(BLANK_ROWS)], \
        longs + [dict(blank_l) for _ in range(BLANK_ROWS)]


def _rows_from_form(form):
    fares = [{"area": form.get(f"fare-{i}-area", ""),
              "distance": form.get(f"fare-{i}-distance", ""),
              "to": form.get(f"fare-{i}-to", ""),
              "from": form.get(f"fare-{i}-from", ""),
              "remove": f"fare-{i}-remove" in form}
             for i in indices(form, "fare")]
    longs = [{"area": form.get(f"long-{i}-area", ""),
              "price": form.get(f"long-{i}-price", ""),
              "remove": f"long-{i}-remove" in form}
             for i in indices(form, "long")]
    return fares, longs


def _is_blank(row, keys):
    return not any(row[k].strip() for k in keys)


def _make_mutator(form):
    fares, longs = _rows_from_form(form)

    def mutate(view):
        errors = []
        tours = view["tours"]
        for t in tours:
            name = f"tour_price__{t['slug']}"
            if name in form:   # unknown slugs in the form are simply never looked at
                v, err = parse_int(form[name], f"Price for {t['name']}", 0, PRICE_MAX,
                                   blank_ok=True)
                if err:
                    errors.append(err)
                else:
                    t["price"] = v
        settings = dict(view["settings"])
        for key, label, lo, hi, money in (
                ("multi_day_rate", "Multi-day rate", 0, PRICE_MAX, True),
                ("extra_hour_rate", "Extra-hour rate", 0, PRICE_MAX, True),
                ("max_passengers", "Max passengers", 1, 20, False)):
            v, err = parse_int(form.get(key, ""), label, lo, hi, money=money)
            if err:
                errors.append(err)
            else:
                settings[key] = v
        out_fares = []
        for n, r in enumerate(fares, 1):
            if r["remove"] or _is_blank(r, ("area", "distance", "to", "from")):
                continue
            area = r["area"].strip()
            label = f"Airport fare row {n}" + (f" ({area})" if area else "")
            if not area:
                errors.append(f"{label}: area is required")
            to, e1 = parse_int(r["to"], f"{label}: price to airport", 0, PRICE_MAX)
            fr, e2 = parse_int(r["from"], f"{label}: price from airport", 0, PRICE_MAX)
            errors += [e for e in (e1, e2) if e]
            out_fares.append({"area": area, "distance": r["distance"].strip(),
                              "to": to, "from": fr})
        out_longs = []
        for n, r in enumerate(longs, 1):
            if r["remove"] or _is_blank(r, ("area", "price")):
                continue
            area = r["area"].strip()
            label = f"Long transfer row {n}" + (f" ({area})" if area else "")
            if not area:
                errors.append(f"{label}: destination is required")
            p, err = parse_int(r["price"], f"{label}: price", 0, PRICE_MAX)
            if err:
                errors.append(err)
            out_longs.append({"area": area, "price": p})
        if errors:
            raise ValidationError(errors)
        return {"tours": tours, "settings": settings,
                "airport_fares": out_fares, "long_transfers": out_longs}
    return mutate


@bp.route("/prices", methods=["GET", "POST"])
@login_required
def prices():
    pub = publisher()
    errors = []
    if request.method == "POST":
        errors = publish(_make_mutator(request.form))
        if not errors:
            flash_ok("Saved. The site is updated.")
            return redirect("/admin/prices")
    c = pub.content()
    if request.method == "POST":
        form = request.form
        fares, longs = _rows_from_form(form)
        values = {t["slug"]: form.get(f"tour_price__{t['slug']}",
                                      "" if t["price"] is None else str(t["price"]))
                  for t in c["tours"]}
        sv = {k: form.get(k, str(c["settings"][k]))
              for k in ("multi_day_rate", "extra_hour_rate", "max_passengers")}
    else:
        fares, longs = _rows_from_content(c)
        values = {t["slug"]: "" if t["price"] is None else str(t["price"])
                  for t in c["tours"]}
        sv = {k: str(c["settings"][k])
              for k in ("multi_day_rate", "extra_hour_rate", "max_passengers")}
    return render_template("admin/prices.html", tours=c["tours"], kinds=KINDS,
                           values=values, sv=sv, fares=fares, longs=longs,
                           errors=errors)
