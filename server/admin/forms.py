"""Shared helpers for the admin editor forms."""
import re

from flask import current_app

from build import BuildError
from content import ValidationError

_MONEY_RE = re.compile(r"^\d+$")


def publisher():
    return current_app.extensions["publisher"]


def publish(mutate):
    """Run Publisher.apply. Returns a list of error strings (empty = saved)."""
    try:
        publisher().apply(mutate)
    except ValidationError as e:
        return e.errors
    except BuildError as e:
        shown = "; ".join(e.broken[:3])
        if len(e.broken) > 3:
            shown += f"; and {len(e.broken) - 3} more"
        return [f"Couldn't publish: {shown}. Nothing was changed."]
    return []


def parse_int(raw, label, lo, hi, *, blank_ok=False, money=True):
    """Parse a whole number. With money=True a leading € and a trailing .00
    are accepted. Returns (value, error)."""
    s = (raw or "").strip()
    if not s:
        return (None, None) if blank_ok else (None, f"{label} can't be empty")
    t = s
    if money:
        if t.startswith("€"):
            t = t[1:].strip()
        if t.endswith(".00"):
            t = t[:-3]
    if not _MONEY_RE.match(t):
        return None, (f"{label}: \"{s}\" isn't a whole number"
                      + (" of euros (digits only, e.g. 450)" if money else ""))
    v = int(t)
    if not lo <= v <= hi:
        return None, f"{label} must be between {lo:,} and {hi:,}"
    return v, None


def indices(form, prefix):
    pat = re.compile(rf"^{re.escape(prefix)}-(\d+)-")
    return sorted({int(m.group(1)) for k in form if (m := pat.match(k))})
