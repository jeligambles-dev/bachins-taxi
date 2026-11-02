import pytest

from content import (SECTIONS, default_content, merge, normalize_vehicle,
                     validate_vehicle)


def test_fleet_section_seeded():
    assert "fleet" in SECTIONS
    fleet = default_content()["fleet"]
    assert [v["slug"] for v in fleet] == ["saloon", "mpv", "van", "minibus"]
    assert [v["passengers"] for v in fleet][:3] == [3, 7, 8]
    assert all(v["published"] and v["photo"] is None for v in fleet)


def test_merge_fleet_replaced_whole_and_normalized():
    out = merge(default_content(), {"fleet": [{"slug": "a", "name": "A"}]})
    assert len(out["fleet"]) == 1
    v = out["fleet"][0]
    assert v["published"] is True and v["features"] == [] and v["photo"] is None
    assert merge(default_content(), {"fleet": []})["fleet"] == []
    assert len(merge(default_content(), {})["fleet"]) == 4


def good(**over):
    v = normalize_vehicle({"slug": "limo", "name": "Limo", "passengers": 4, "bags": 2})
    v.update(over)
    return v


def test_validate_vehicle_ok():
    assert validate_vehicle(good(), []) == []


@pytest.mark.parametrize("over", [
    dict(slug="Bad Slug"), dict(slug=""), dict(name="  "), dict(name="x" * 81),
    dict(example="x" * 121), dict(desc="x" * 401), dict(price_note="x" * 81),
    dict(features=["a"] * 7), dict(features=["x" * 81]),
    dict(passengers=0), dict(passengers=61), dict(passengers="3"),
    dict(passengers=True), dict(bags=-1), dict(bags=61),
])
def test_validate_vehicle_rejects(over):
    assert validate_vehicle(good(**over), [])


def test_validate_vehicle_unique_slug():
    assert validate_vehicle(good(slug="van"), default_content()["fleet"])
