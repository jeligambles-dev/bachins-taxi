"""Shared helpers for the admin editor forms."""
import logging
import re

from flask import current_app

from build import BuildError
from content import ValidationError

_MONEY_RE = re.compile(r"^[0-9]+$", re.ASCII)
SHORT_MAX = 200
TEXT_MAX = 2000
log = logging.getLogger("bch.admin")



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
    except Exception:
        log.exception("publish failed")
        return ["Couldn't publish: something went wrong building the site. "
                "Nothing was changed."]
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
    v = int(t) if len(t) <= 12 else hi + 1   # never int() a huge string
    if not lo <= v <= hi:
        return None, f"{label} must be between {lo:,} and {hi:,}"
    return v, None


def indices(form, prefix):
    pat = re.compile(rf"^{re.escape(prefix)}-([0-9]{{1,4}})-", re.ASCII)
    return sorted({int(m.group(1)) for k in form if (m := pat.match(k))})


def too_long(value, label, limit=SHORT_MAX):
    if len(value) > limit:
        return f"{label} is too long (max {limit:,} characters)"
    return None


def digest(value):
    """Short stable fingerprint of a string or JSON-able value."""
    import hashlib
    import json
    raw = value if isinstance(value, str) else json.dumps(value, sort_keys=True,
                                                          ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
