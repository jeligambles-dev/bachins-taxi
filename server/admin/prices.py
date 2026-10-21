"""/admin/prices: tour prices, rates, airport fares, long transfers."""
from flask import redirect, render_template, request

from content import KINDS, ValidationError

from . import bp
from .auth import flash_ok, login_required
from .forms import (SHORT_MAX, digest, indices, parse_int, publish, publisher,
                    too_long)

PRICE_MAX = 100000
RATE_KEYS = ("multi_day_rate", "extra_hour_rate", "max_passengers")
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


def _canon_fares(fares):
    return [{"area": f["area"], "distance": f.get("distance") or "",
             "to": int(f["to"]), "from": int(f["from"])} for f in fares]


def _canon_longs(longs):
    return [{"area": f["area"], "price": int(f["price"])} for f in longs]


def _is_blank(row, keys):
    return not any(row[k].strip() for k in keys)


def _touched(form, name, shown):
    """True unless the field still holds the value it was rendered with."""
    orig = form.get("o__" + name)
    return orig is None or orig.strip() != shown.strip()


def _make_mutator(form):
    fares, longs = _rows_from_form(form)

    def mutate(view):
        errors = []
        tours = view["tours"]
        for t in tours:
            name = f"tour_price__{t['slug']}"
            # unknown slugs in the form are never looked at; untouched fields
            # keep their fresh value (another tab may have changed them)
            if name in form and _touched(form, name, form[name]):
                err = too_long(form[name], f"Price for {t['name']}")
                v, err2 = parse_int(form[name], f"Price for {t['name']}", 0, PRICE_MAX,
                                    blank_ok=True)
                if err or err2:
                    errors.append(err or err2)
                else:
                    t["price"] = v
        settings = dict(view["settings"])
        for key, label, lo, hi, money in (
                ("multi_day_rate", "Multi-day rate", 0, PRICE_MAX, True),
                ("extra_hour_rate", "Extra-hour rate", 0, PRICE_MAX, True),
                ("max_passengers", "Max passengers", 1, 20, False)):
            if not _touched(form, key, form.get(key, "")):
                continue
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
            errors += [e for e in (too_long(area, f"{label}: area"),
                                   too_long(r["distance"], f"{label}: distance")) if e]
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
            err = too_long(area, f"{label}: destination")
            if err:
                errors.append(err)
            p, err = parse_int(r["price"], f"{label}: price", 0, PRICE_MAX)
            if err:
                errors.append(err)
            out_longs.append({"area": area, "price": p})
        if errors:
            raise ValidationError(errors)
        result_fares, result_longs = view["airport_fares"], view["long_transfers"]
        for name, submitted, fresh, canon in (
                ("fares", out_fares, view["airport_fares"], _canon_fares),
                ("longs", out_longs, view["long_transfers"], _canon_longs)):
            v = form.get(name + "_v")
            if v is not None and digest(submitted) == v:
                continue    # list untouched: keep the fresh one
            if v is not None and digest(canon(fresh)) != v:
                raise ValidationError([
                    ("Airport fares" if name == "fares" else "Long transfers")
                    + " were changed in another tab or device. "
                      "Reload the page and try again."])
            if name == "fares":
                result_fares = submitted
            else:
                result_longs = submitted
        if not result_fares:
            raise ValidationError(["Keep at least one airport fare. The homepage "
                                   "and calculator need one."])
        return {"tours": tours, "settings": settings,
                "airport_fares": result_fares, "long_transfers": result_longs}
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
    blank_f = {"area": "", "distance": "", "to": "", "from": "", "remove": False}
    blank_l = {"area": "", "price": "", "remove": False}
    shown_tours = {t["slug"]: "" if t["price"] is None else str(t["price"])
                   for t in c["tours"]}
    shown_rates = {k: str(c["settings"][k]) for k in RATE_KEYS}
    if request.method == "POST":
        form = request.form
        fares, longs = _rows_from_form(form)
        # drop trailing blank rows, then offer 2 fresh ones
        while fares and not fares[-1]["remove"] and _is_blank(fares[-1], blank_f.keys() - {"remove"}):
            fares.pop()
        while longs and not longs[-1]["remove"] and _is_blank(longs[-1], ("area", "price")):
            longs.pop()
        fares += [dict(blank_f) for _ in range(BLANK_ROWS)]
        longs += [dict(blank_l) for _ in range(BLANK_ROWS)]
        values = {s: form.get(f"tour_price__{s}", v) for s, v in shown_tours.items()}
        sv = {k: form.get(k, v) for k, v in shown_rates.items()}
        orig = {("tour_price__" + s): form.get("o__tour_price__" + s, v)
                for s, v in shown_tours.items()}
        orig.update({k: form.get("o__" + k, v) for k, v in shown_rates.items()})
        fares_v = form.get("fares_v") or digest(_canon_fares(c["airport_fares"]))
        longs_v = form.get("longs_v") or digest(_canon_longs(c["long_transfers"]))
    else:
        fares, longs = _rows_from_content(c)
        values, sv = shown_tours, shown_rates
        orig = {("tour_price__" + s): v for s, v in shown_tours.items()}
        orig.update(shown_rates)
        fares_v = digest(_canon_fares(c["airport_fares"]))
        longs_v = digest(_canon_longs(c["long_transfers"]))
    return render_template("admin/prices.html", tours=c["tours"], kinds=KINDS,
                           values=values, sv=sv, fares=fares, longs=longs,
                           orig=orig, fares_v=fares_v, longs_v=longs_v,
                           short_max=SHORT_MAX, errors=errors)
