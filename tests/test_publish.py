import os
import threading
from pathlib import Path

import pytest

import build
from content import ValidationError
from server.publish import Publisher


def _releases(root):
    d = Path(root) / "releases"
    return sorted(p for p in d.iterdir()) if d.exists() else []


def _target(root):
    return (Path(root) / "current").resolve()


def test_rebuild_creates_current(store, tmp_path):
    pub = Publisher(store, tmp_path)
    assert pub.current_dir() is None
    pub.rebuild()
    assert (tmp_path / "current" / "index.html").exists()
    assert pub.current_dir() == _target(tmp_path)
    assert "settings" in pub.content() and "redirects" in pub.content()


def test_apply_success_saves_and_swaps(store, tmp_path):
    pub = Publisher(store, tmp_path)
    pub.rebuild()
    pub.apply(lambda v: {"settings": {**v["settings"], "email": "new@example.com"}})
    assert "new@example.com" in (tmp_path / "current" / "js" / "config.js").read_text()
    assert store.load()["settings"]["email"] == "new@example.com"
    assert pub.content()["settings"]["email"] == "new@example.com"


def test_apply_build_failure_keeps_old(store, tmp_path, monkeypatch):
    pub = Publisher(store, tmp_path)
    pub.rebuild()
    before, db, rel = _target(tmp_path), store.load(), _releases(tmp_path)

    made = []

    def boom(content, out_dir, **k):
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "partial.html").write_text("x")
        made.append(Path(out_dir))
        raise build.BuildError(["x: y"])
    monkeypatch.setattr("server.publish.build_site", boom)
    with pytest.raises(build.BuildError):
        pub.apply(lambda v: {"settings": {**v["settings"], "email": "z@example.com"}})
    assert made and not made[0].exists()
    assert _target(tmp_path) == before
    assert store.load() == db
    assert _releases(tmp_path) == rel
    assert pub.content()["settings"]["email"] != "z@example.com"


def test_apply_validation_error_keeps_old(store, tmp_path):
    pub = Publisher(store, tmp_path)
    pub.rebuild()
    before, rel = _target(tmp_path), _releases(tmp_path)

    def bad(view):
        raise ValidationError(["nope"])
    with pytest.raises(ValidationError) as ei:
        pub.apply(bad)
    assert ei.value.errors == ["nope"]
    assert _target(tmp_path) == before and _releases(tmp_path) == rel


def test_save_failure_deletes_release_and_keeps_current(store, tmp_path, monkeypatch):
    pub = Publisher(store, tmp_path)
    pub.rebuild()
    before, rel = _target(tmp_path), _releases(tmp_path)

    def fail(changes):
        raise RuntimeError("db down")
    monkeypatch.setattr(store, "save_sections", fail)
    with pytest.raises(RuntimeError, match="db down"):
        pub.apply(lambda v: {"settings": {**v["settings"], "email": "q@example.com"}})
    assert _target(tmp_path) == before and _releases(tmp_path) == rel


def test_apply_patches_only_changed_sections(store, tmp_path):
    pub = Publisher(store, tmp_path)
    pub.rebuild()
    stale = pub.content()
    store.save_sections({"texts": {"cta.text": "Kept Title"}})
    seen = {}

    def mutate(view):
        seen["v"] = view
        return {"settings": {**stale["settings"], "email": "s@example.com"}}
    pub.apply(mutate)
    assert seen["v"]["texts"]["cta.text"] == "Kept Title"
    stored = store.load()
    assert stored["texts"] == {"cta.text": "Kept Title"}
    assert stored["settings"]["email"] == "s@example.com"
    assert set(stored) == {"texts", "settings"}


def test_old_releases_pruned(store, tmp_path):
    pub = Publisher(store, tmp_path)
    for i in range(5):
        pub.apply(lambda v, i=i: {"settings": {**v["settings"], "email": f"e{i}@example.com"}})
    rels = _releases(tmp_path)
    assert len(rels) <= 3
    assert _target(tmp_path) in [r.resolve() for r in rels]


def test_photo_filenames_are_content_hashed(store, tmp_path):
    pub = Publisher(store, tmp_path)
    a = store.add_photo(b"\xff\xd8\xffAAAA", "image/jpeg", 10, 10, "a.jpg")
    b = store.add_photo(b"\x89PNG\r\n\x1a\nBBBB", "image/png", 10, 10, "b.png")
    pub.apply(lambda v: {"photo_slots": {**v["photo_slots"], "hero": a["id"]}})
    names1 = {p.name for p in (tmp_path / "current" / "uploads").iterdir()}
    html1 = (tmp_path / "current" / "index.html").read_text()
    assert f"uploads/{a['sha'][:12]}.jpg" in html1
    pub.apply(lambda v: {"photo_slots": {**v["photo_slots"], "hero": b["id"]}})
    html2 = (tmp_path / "current" / "index.html").read_text()
    assert f"uploads/{b['sha'][:12]}.png" in html2
    assert f"{a['sha'][:12]}.jpg" not in html2
    assert f"{a['sha'][:12]}.jpg" in names1


def test_concurrent_applies_serialize(store, tmp_path):
    pub = Publisher(store, tmp_path)
    pub.rebuild()
    errs = []

    def run(key):
        try:
            pub.apply(lambda v: {"texts": {**v["texts"], key: f"val-{key}"}})
        except Exception as e:  # pragma: no cover
            errs.append(e)
    ts = [threading.Thread(target=run, args=(k,)) for k in ("cta.text", "cta.title")]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs
    texts = store.load()["texts"]
    assert texts["cta.text"] == "val-cta.text" and texts["cta.title"] == "val-cta.title"
    assert (tmp_path / "current" / "index.html").exists()
    assert pub.content()["texts"]["cta.title"] == "val-cta.title"


def test_relative_site_root_resolves(store, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pub = Publisher(store, "rel-site")
    pub.rebuild()
    assert pub.current_dir() is not None
    assert (pub.current_dir() / "index.html").exists()
    assert (Path("rel-site") / "current" / "index.html").exists()


def test_content_returns_copy(store, tmp_path):
    pub = Publisher(store, tmp_path)
    pub.rebuild()
    c = pub.content()
    c["settings"]["email"] = "mutated@example.com"
    assert pub.content()["settings"]["email"] != "mutated@example.com"


def test_prune_by_creation_order(store, tmp_path, monkeypatch):
    import server.publish as sp
    monkeypatch.setattr(sp.secrets, "token_hex", lambda n=2: "ffff" if n == 2 else "0" * (2 * n))
    pub = Publisher(store, tmp_path)
    for i in range(6):
        pub.apply(lambda v, i=i: {"settings": {**v["settings"], "email": f"e{i}@example.com"}})
    kept = [p.name for p in _releases(tmp_path)]
    assert len(kept) == 3
    assert _target(tmp_path).name == kept[-1] == sorted(kept)[-1]
