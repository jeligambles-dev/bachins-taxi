from content import (SECTIONS, default_content, merge, price_label,
                     validate_tour, normalize_tour)


def test_default_content_has_all_sections():
    assert set(default_content()) == set(SECTIONS)


def test_seeded_day_tours_unchanged():
    tours = default_content()["tours"]
    day = [t for t in tours if t["kind"] == "day"]
    assert len(day) == 12
    kerry = next(t for t in tours if t["slug"] == "ring-of-kerry")
    assert kerry["price"] == 460


def test_starter_pub_and_golf_unpriced():
    by = {t["slug"]: t for t in default_content()["tours"]}
    for slug in ("meath-boyne-pub-trail", "wicklow-country-pubs",
                 "dublin-links-golf-day", "south-west-links-golf-trip"):
        assert slug in by
        assert by[slug]["price"] is None


def test_merge_settings_per_key():
    d = default_content()
    out = merge(d, {"settings": {"email": "a@b.ie"}})
    assert out["settings"]["email"] == "a@b.ie"
    assert out["settings"]["phone"] == d["settings"]["phone"]


def test_merge_new_default_text_key_survives():
    d = default_content()
    d["texts"] = {"x": "1", "y": "2"}
    assert merge(d, {"texts": {"x": "9"}})["texts"] == {"x": "9", "y": "2"}


def test_merge_tours_replaced_and_normalized():
    out = merge(default_content(), {"tours": [{"slug": "a", "name": "A"}]})
    assert len(out["tours"]) == 1
    assert out["tours"][0]["published"] is True
    assert out["tours"][0]["kind"] == "day"


def test_merge_ignores_unknown_keys():
    assert "bogus" not in merge(default_content(), {"bogus": 1})


def test_price_label():
    assert price_label({"price": None}) == "Price on request"
    assert price_label({"price": 1234}) == "€1,234"


def test_validate_tour_errors():
    good = normalize_tour({"slug": "ok", "name": "Ok"})
    assert validate_tour(good, []) == []
    assert validate_tour({**good, "slug": "Bad Slug"}, [])
    assert validate_tour(good, [{"slug": "ok"}])
    assert validate_tour({**good, "name": "  "}, [])
    assert validate_tour({**good, "price": -1}, [])
    assert validate_tour({**good, "price": "abc"}, [])
    assert validate_tour({**good, "kind": "boat"}, [])
