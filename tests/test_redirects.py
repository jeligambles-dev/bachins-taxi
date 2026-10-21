import pytest

import build
from content import (ValidationError, blog_links_to, default_content, merge,
                     rename_slug)


def _sections(*slugs):
    tours = [dict(default_content()["tours"][0], slug=s, name=s) for s in slugs]
    return {"tours": tours, "redirects": {}}


def _apply(sec, old, new):
    r = rename_slug(sec, old, new)
    return {"tours": r["tours"], "redirects": r["redirects"]}


def test_rename_rewrites_blog_links(tmp_path):
    base = default_content()
    sec = _apply({"tours": base["tours"], "redirects": {}}, "ring-of-kerry", "kerry-ring")
    c = merge(base, sec)
    build.build_site(c, tmp_path)
    post = (tmp_path / "blog/best-day-trips-from-dublin.html").read_text()
    assert "../tours/kerry-ring.html" in post
    assert "ring-of-kerry" not in post
    assert (tmp_path / "tours/kerry-ring.html").exists()


def test_rename_chain():
    s = _apply(_sections("a"), "a", "b")
    s = _apply(s, "b", "c")
    assert s["redirects"] == {"a": "c", "b": "c"}
    assert [t["slug"] for t in s["tours"]] == ["c"]


def test_rename_back_reuses_slug():
    s = _apply(_sections("a"), "a", "b")
    s = _apply(s, "b", "a")
    assert s["redirects"] == {"b": "a"}


def test_rename_errors():
    sec = _sections("a", "b")
    for old, new in (("zzz", "q"), ("a", "b"), ("a", "Bad Slug")):
        with pytest.raises(ValidationError):
            rename_slug(sec, old, new)
    assert rename_slug(sec, "a", "a")["redirects"] == {}


def test_rename_does_not_mutate_input():
    sec = _sections("a")
    rename_slug(sec, "a", "b")
    assert sec["tours"][0]["slug"] == "a" and sec["redirects"] == {}


def test_blog_links_to():
    assert blog_links_to("cliffs-of-moher", {})
    assert blog_links_to("meath-boyne-pub-trail", {}) == []
    assert blog_links_to("kerry-ring", {"ring-of-kerry": "kerry-ring"})
    assert blog_links_to("ring-of-kerry", {"ring-of-kerry": "kerry-ring"}) == []
