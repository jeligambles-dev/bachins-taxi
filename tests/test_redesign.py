"""Dark executive redesign (docs/superpowers/specs/2026-11-08-dark-executive-redesign-design.md)."""
from pathlib import Path

import build
from content import default_content, merge


def _build(tmp_path, content=None):
    build.build_site(content or merge(default_content(), {}), tmp_path)
    return tmp_path


def test_every_page_loads_serif_font(tmp_path):
    _build(tmp_path)
    pages = list(Path(tmp_path).rglob("*.html"))
    assert len(pages) > 10
    for p in pages:
        head = p.read_text().split("</head>")[0]
        assert "family=Instrument+Serif" in head, p
        assert "family=Geist" in head, p
