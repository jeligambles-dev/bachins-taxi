import io

from tests.conftest import csrf_of


def pub(app):
    return app.extensions["publisher"]


def vehicle(app, slug):
    return next((v for v in pub(app).content()["fleet"] if v["slug"] == slug), None)


def post(c, url, **data):
    data["csrf"] = csrf_of(c)
    return c.post(url, data=data)


def full(app, slug, **over):
    """A complete, unchanged submission for an existing vehicle (with o__ fields)."""
    from server.admin.fleet import orig_values, shown_values
    v = shown_values(vehicle(app, slug))
    d = {k: val for k, val in v.items() if k != "published"}
    if vehicle(app, slug)["published"]:
        d["published"] = "1"
    for k, val in orig_values(v).items():
        d["o__" + k] = val
    d.update(over)
    return d


def new_car(c, **over):
    d = dict(name="Test Coach", slug="test-coach", passengers="30", bags="20",
             example="A coach", desc="Big.", features="Toilet\nWi-Fi", published="1")
    d.update(over)
    return post(c, "/admin/fleet/new", **d)


def photo(app):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(buf, "JPEG")
    return pub(app).store.add_photo(buf.getvalue(), "image/jpeg", 8, 8, "v.jpg")


def test_requires_login(client):
    assert client.get("/admin/fleet").status_code == 302
    assert client.get("/admin/fleet/new").status_code == 302


def test_nav_and_dashboard_link_fleet(logged_in):
    assert "/admin/fleet" in logged_in.get("/admin/").get_data(as_text=True)
    h = logged_in.get("/admin/fleet").get_data(as_text=True)
    assert 'href="/admin/fleet" aria-current="page"' in h


def test_list_shows_seeded_vehicles(logged_in):
    h = logged_in.get("/admin/fleet").get_data(as_text=True)
    for n in ("Executive saloon", "Premium MPV", "8-seater van", "Minibus / coach"):
        assert n.replace("/", "/") in h
    assert "/admin/fleet/new" in h


def test_create_appears_on_site_and_booking_card(logged_in, app):
    r = new_car(logged_in)
    assert r.status_code == 302
    v = vehicle(app, "test-coach")
    assert v["passengers"] == 30 and v["features"] == ["Toilet", "Wi-Fi"] and v["published"]
    assert "Test Coach" in logged_in.get("/fleet.html").get_data(as_text=True)
    idx = logged_in.get("/index.html").get_data(as_text=True)
    assert "Test Coach (up to 30)" in idx


def test_auto_slug_and_unique_suffix(logged_in, app):
    new_car(logged_in, slug="", name="Big  Bus!")
    assert vehicle(app, "big-bus")
    new_car(logged_in, slug="", name="Big Bus")
    assert vehicle(app, "big-bus-2")
    new_car(logged_in, slug="", name="New")
    assert vehicle(app, "new-2") and not vehicle(app, "new")


def test_duplicate_slug_and_bad_slug_rerender(logged_in, app):
    r = new_car(logged_in, slug="van")
    assert r.status_code == 200 and b"already uses" in r.data and b"Test Coach" in r.data
    assert len([v for v in pub(app).content()["fleet"] if v["slug"] == "van"]) == 1
    assert new_car(logged_in, slug="Bad Slug").status_code == 200


def test_validation_rerenders_200_and_saves_nothing(logged_in, app):
    n = len(pub(app).content()["fleet"])
    for over in (dict(name=""), dict(name="x" * 81), dict(example="x" * 121),
                 dict(desc="x" * 401), dict(price_note="x" * 81),
                 dict(features="\n".join(f"f{i}" for i in range(7))),
                 dict(features="y" * 81), dict(passengers="0"), dict(passengers="61"),
                 dict(passengers="abc"), dict(bags="-1"), dict(bags="61"),
                 dict(photo="nope")):
        r = new_car(logged_in, **over)
        assert r.status_code == 200, over
    assert len(pub(app).content()["fleet"]) == n


def test_huge_numbers_no_500(logged_in, app):
    for v in ("9" * 400, "1e999", "０１２", "-" + "9" * 50, " "):
        assert new_car(logged_in, passengers=v).status_code == 200
        assert new_car(logged_in, bags=v).status_code == 200
        r = post(logged_in, "/admin/fleet/van", **full(app, "van", passengers=v))
        assert r.status_code == 200
    assert vehicle(app, "van")["passengers"] == 8


def test_edit_and_stale_tab_does_not_undo(logged_in, app):
    d = full(app, "van")                          # stale snapshot
    pub(app).apply(lambda v: {"fleet": [dict(x, desc="NEWER DESC", bags=12)
                                        if x["slug"] == "van" else x for x in v["fleet"]]})
    d["name"] = "Van Renamed"
    assert post(logged_in, "/admin/fleet/van", **d).status_code == 302
    v = vehicle(app, "van")
    assert v["name"] == "Van Renamed" and v["desc"] == "NEWER DESC" and v["bags"] == 12


def test_edit_deleted_vehicle(logged_in, app):
    d = full(app, "mpv")
    pub(app).apply(lambda v: {"fleet": [x for x in v["fleet"] if x["slug"] != "mpv"]})
    d["name"] = "X"
    r = post(logged_in, "/admin/fleet/mpv", **d)
    assert r.status_code == 200
    assert b"This vehicle was deleted in another tab or device." in r.data
    assert logged_in.get("/admin/fleet/mpv").status_code == 404


def test_edit_form_renders_originals_and_slug_readonly(logged_in):
    h = logged_in.get("/admin/fleet/van").get_data(as_text=True)
    assert 'name="o__name"' in h and 'name="o__features"' in h
    assert 'name="slug"' not in h


def test_hide_and_show(logged_in, app):
    assert post(logged_in, "/admin/fleet/mpv/publish", published="0").status_code == 302
    assert vehicle(app, "mpv")["published"] is False
    post(logged_in, "/admin/fleet/mpv/publish", published="0")      # idempotent
    assert "Hidden" in logged_in.get("/admin/fleet").get_data(as_text=True)
    assert "Premium MPV" not in logged_in.get("/fleet.html").get_data(as_text=True)
    assert "Premium MPV" not in logged_in.get("/index.html").get_data(as_text=True)
    post(logged_in, "/admin/fleet/mpv/publish", published="1")
    assert vehicle(app, "mpv")["published"] is True
    r = post(logged_in, "/admin/fleet/ghost/publish", published="0")
    assert r.status_code == 302       # flash, no 500


def test_delete_needs_confirmation(logged_in, app):
    h = logged_in.get("/admin/fleet/minibus/delete").get_data(as_text=True)
    assert "Delete" in h and "Minibus / coach" in h
    assert vehicle(app, "minibus")            # GET never deletes
    assert post(logged_in, "/admin/fleet/minibus/delete").status_code == 302
    assert vehicle(app, "minibus") is None
    assert "Minibus / coach" not in logged_in.get("/fleet.html").get_data(as_text=True)
    assert logged_in.get("/admin/fleet/minibus/delete").status_code == 404
    r = post(logged_in, "/admin/fleet/minibus/delete")      # already gone
    assert r.status_code == 200 and b"deleted in another tab" in r.data


def test_delete_all_vehicles_still_builds(logged_in, app):
    for s in ("saloon", "mpv", "van", "minibus"):
        assert post(logged_in, f"/admin/fleet/{s}/delete").status_code == 302
    assert pub(app).content()["fleet"] == []
    assert logged_in.get("/fleet.html").status_code == 200
    assert 'id="cf-vehicle"' not in logged_in.get("/index.html").get_data(as_text=True)


def test_photo_pick_and_used_by(logged_in, app):
    p = photo(app)
    h = logged_in.get("/admin/fleet/van").get_data(as_text=True)
    assert f"/admin/photos/{p['id']}/raw" in h and "No photo" in h
    assert post(logged_in, "/admin/fleet/van", **full(app, "van", photo=p["id"])).status_code == 302
    assert vehicle(app, "van")["photo"] == p["id"]
    assert "uploads/" in logged_in.get("/fleet.html").get_data(as_text=True)
    # photo page says who uses it, and deletion is blocked
    assert "8-seater van (vehicle)" in logged_in.get("/admin/photos").get_data(as_text=True)
    r = post(logged_in, f"/admin/photos/{p['id']}/delete")
    assert r.status_code == 200 and b"8-seater van" in r.data
    assert pub(app).store.get_photo(p["id"])
    # clear, then it can go
    assert post(logged_in, "/admin/fleet/van", **full(app, "van", photo="")).status_code == 302
    assert post(logged_in, f"/admin/photos/{p['id']}/delete").status_code == 302


def test_hidden_vehicle_still_blocks_photo_delete(logged_in, app):
    p = photo(app)
    post(logged_in, "/admin/fleet/van", **full(app, "van", photo=p["id"]))
    post(logged_in, "/admin/fleet/van/publish", published="0")
    r = post(logged_in, f"/admin/photos/{p['id']}/delete")
    assert r.status_code == 200 and pub(app).store.get_photo(p["id"])


def test_photo_field_missing_keeps_and_missing_photo_roundtrips(logged_in, app):
    p = photo(app)
    post(logged_in, "/admin/fleet/van", **full(app, "van", photo=p["id"]))
    d = full(app, "van", name="Renamed")
    d.pop("photo"); d.pop("o__photo")
    assert post(logged_in, "/admin/fleet/van", **d).status_code == 302
    assert vehicle(app, "van")["photo"] == p["id"]
    pub(app).apply(lambda v: {"fleet": [dict(x, photo="gone123") if x["slug"] == "van" else x
                                        for x in v["fleet"]]})
    h = logged_in.get("/admin/fleet/van").get_data(as_text=True)
    assert "(missing photo)" in h and 'value="gone123" checked' in h


def test_owner_text_escaped_in_admin_and_site(logged_in, app):
    evil = '<img src=x onerror=alert(1)>'
    new_car(logged_in, name=evil, example=evil, desc=evil, price_note=evil, features=evil)
    for url in ("/admin/fleet", "/admin/fleet/test-coach", "/fleet.html", "/index.html"):
        pass
    slug = [v["slug"] for v in pub(app).content()["fleet"] if v["name"] == evil][0]
    for url in ("/admin/fleet", f"/admin/fleet/{slug}", f"/admin/fleet/{slug}/delete",
                "/fleet.html", "/index.html"):
        h = logged_in.get(url).get_data(as_text=True)
        assert "<img src=x onerror" not in h, url


def test_fleet_text_keys_editable_in_admin_text_page(logged_in):
    h = logged_in.get("/admin/text").get_data(as_text=True)
    for k in ("fleet.title", "business.benefits", "partners.who", "help.changes_text"):
        assert f"t__{k}" in h, k
