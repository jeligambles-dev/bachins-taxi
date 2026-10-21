import pytest


def test_migrate_idempotent(store):
    store.migrate()
    store.migrate()
    assert store.load() == {}


def test_save_and_load_sections(store):
    store.save_sections({"settings": {"phone": "1"}, "flags": ["a", 2]})
    assert store.load() == {"settings": {"phone": "1"}, "flags": ["a", 2]}
    store.save_sections({"settings": {"phone": "2"}})
    assert store.load()["settings"] == {"phone": "2"}
    assert store.load()["flags"] == ["a", 2]


def test_save_none_deletes(store):
    store.save_sections({"a": {"x": 1}, "b": 2})
    store.save_sections({"a": None})
    assert store.load() == {"b": 2}


def test_save_sections_atomic(store, monkeypatch):
    calls = []
    orig = store._upsert

    def flaky(cur, key, value):
        calls.append(key)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return orig(cur, key, value)

    monkeypatch.setattr(store, "_upsert", flaky)
    with pytest.raises(RuntimeError):
        store.save_sections({"a": 1, "b": 2})
    monkeypatch.undo()
    assert store.load() == {}


def test_add_photo_dedupes_by_sha(store):
    p1 = store.add_photo(b"abc", "image/jpeg", 10, 20, "a.jpg")
    p2 = store.add_photo(b"abc", "image/jpeg", 10, 20, "b.jpg")
    assert p1["id"] == p2["id"] and len(p1["id"]) == 12
    assert len(p1["sha"]) == 64
    assert len(store.list_photos()) == 1
    got = store.get_photo(p1["id"])
    assert got["data"] == b"abc" and got["original_name"] == "a.jpg"
    assert isinstance(got["created_at"], str)
    store.delete_photo(p1["id"])
    assert store.get_photo(p1["id"]) is None


def test_list_photos_excludes_data(store):
    a = store.add_photo(b"1", "image/jpeg", 1, 1, "a")
    b = store.add_photo(b"2", "image/png", 2, 2, "b")
    rows = store.list_photos()
    assert [r["id"] for r in rows] == [b["id"], a["id"]]
    assert all("data" not in r for r in rows)
    assert set(rows[0]) == {"id", "sha", "mime", "width", "height", "original_name", "created_at"}
