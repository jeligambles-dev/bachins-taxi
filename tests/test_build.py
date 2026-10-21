import hashlib
from pathlib import Path

import pytest

import build
from content import default_content, merge

TEMPLATE = Path(build.__file__).resolve().parent / "templates" / "index.html"


def _content():
    return merge(default_content(), {})


def test_build_site_writes_pages(tmp_path):
    build.build_site(_content(), tmp_path)
    for rel in ("index.html", "tours/ring-of-kerry.html",
                "price-calculator.html", "css/style.css"):
        assert (tmp_path / rel).exists(), rel


def test_template_never_modified(tmp_path):
    before = hashlib.sha256(TEMPLATE.read_bytes()).hexdigest()
    build.build_site(_content(), tmp_path)
    assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == before


def test_build_error_on_broken_link(tmp_path, monkeypatch):
    post = dict(build.POSTS[0])
    post["body"] = post["body"] + '<a href="{ROOT}tours/nope.html">x</a>'
    monkeypatch.setattr(build, "POSTS", [post] + list(build.POSTS[1:]))
    with pytest.raises(build.BuildError) as ei:
        build.build_site(_content(), tmp_path)
    assert any("tours/nope.html" in b for b in ei.value.broken)
