import io

import pytest

from tests.conftest import csrf_of


def pub(app):
    return app.extensions["publisher"]


def tour(app, slug):
    return next((t for t in pub(app).content()["tours"] if t["slug"] == slug), None)


def post(c, url, **data):
    data["csrf"] = csrf_of(c)
    return c.post(url, data=data)


def edit_form(c, app, slug):
    """Fields as a browser would submit them for the unchanged edit form."""
    import re
    html = c.get(f"/admin/tours/{slug}").get_data(as_text=True)
    return html


def full(app, which, **over):
    """A complete, unchanged submission for an existing tour (with o__ fields)."""
    from server.admin.tours import shown_values, orig_values
    t = tour(app, which)
    v = shown_values(t)
    d = {k: val for k, val in v.items() if k not in ("published", "fav")}
    if t["published"]:
        d["published"] = "1"
    if t["fav"]:
        d["fav"] = "1"
    for k, val in orig_values(v).items():
        d["o__" + k] = val
    d.update(over)
    return d


def new_golf(c, **over):
    d = dict(kind="golf", name="Test Golf", slug="test-golf", price="950",
             region="Co. Dublin", published="1")
    d.update(over)
    return post(c, "/admin/tours/new", **d)


def test_list_groups_and_buttons(logged_in):
    h = logged_in.get("/admin/tours").get_data(as_text=True)
    assert "Day tours" in h and "Rural pub tours" in h and "Golf trips" in h
    assert "/admin/tours/new?kind=pub" in h and "Price on request" in h or "€" in h
    assert "Giant&#39;s Causeway" in h


def test_new_golf_trip_appears(logged_in, app):
    r = new_golf(logged_in)
    assert r.status_code == 302
    assert "golf" in logged_in.get("/golf-trips.html").get_data(as_text=True).lower()
    assert "Test Golf" in logged_in.get("/golf-trips.html").get_data(as_text=True)
    page = logged_in.get("/tours/test-golf.html").get_data(as_text=True)
    assert "€950" in page and "per trip" in page


def test_new_tour_auto_slug_and_suffix(logged_in, app):
    new_golf(logged_in, slug="", name="Fancy  Links & Lunch!")
    assert tour(app, "fancy-links-lunch")
    new_golf(logged_in, slug="", name="Fancy Links Lunch")
    assert tour(app, "fancy-links-lunch-2")
    t = tour(app, "fancy-links-lunch")
    assert t["published"] is True


def test_new_tour_blank_price_none(logged_in, app):
    new_golf(logged_in, price="")
    assert tour(app, "test-golf")["price"] is None
    assert "Price on request" in logged_in.get("/tours/test-golf.html").get_data(as_text=True)


def test_new_tour_drops_matching_redirect(logged_in, app):
    pub(app).apply(lambda v: {"redirects": {"test-golf": "giants-causeway"}})
    new_golf(logged_in)
    assert "test-golf" not in pub(app).content()["redirects"]


def test_duplicate_slug_rejected(logged_in, app):
    r = new_golf(logged_in, slug="giants-causeway")
    assert r.status_code == 200
    assert b"already uses" in r.data
    assert b"Test Golf" in r.data       # submitted values kept
    assert len([t for t in pub(app).content()["tours"] if t["slug"] == "giants-causeway"]) == 1


def test_bad_price_rejected(logged_in):
    r = new_golf(logged_in, price="12abc")
    assert r.status_code == 200 and b"whole number" in r.data
    r = new_golf(logged_in, price="9" * 400)
    assert r.status_code == 200


def test_edit_highlights_lines(logged_in, app):
    d = full(app, "giants-causeway", highlights="  One \r\n\r\nTwo\n   \nThree  ")
    assert post(logged_in, "/admin/tours/giants-causeway", **d).status_code == 302
    assert tour(app, "giants-causeway")["highlights"] == ["One", "Two", "Three"]
    d = full(app, "giants-causeway", highlights="\n".join(f"h{i}" for i in range(13)))
    r = post(logged_in, "/admin/tours/giants-causeway", **d)
    assert r.status_code == 200 and b"12" in r.data
    assert len(tour(app, "giants-causeway")["highlights"]) == 3


def test_edit_form_renders_originals(logged_in):
    h = logged_in.get("/admin/tours/giants-causeway").get_data(as_text=True)
    assert 'name="o__name"' in h and 'name="o__highlights"' in h
    assert "This is the web address. Changing it keeps the old address working." in h


def test_stale_tab_does_not_undo(logged_in, app):
    d = full(app, "giants-causeway")            # stale snapshot
    pub(app).apply(lambda v: {"tours": [dict(t, intro="NEWER INTRO", price=777)
                                        if t["slug"] == "giants-causeway" else t
                                        for t in v["tours"]]})
    d["name"] = "Causeway Renamed"
    assert post(logged_in, "/admin/tours/giants-causeway", **d).status_code == 302
    t = tour(app, "giants-causeway")
    assert t["name"] == "Causeway Renamed"
    assert t["intro"] == "NEWER INTRO" and t["price"] == 777


def test_edit_deleted_tour(logged_in, app):
    s = "meath-boyne-pub-trail"
    d = full(app, s)
    pub(app).apply(lambda v: {"tours": [t for t in v["tours"] if t["slug"] != s]})
    d["name"] = "X"
    r = post(logged_in, f"/admin/tours/{s}", **d)
    assert r.status_code == 200
    assert b"This tour was deleted in another tab or device." in r.data


def test_hide_toggle(logged_in, app):
    r = post(logged_in, "/admin/tours/giants-causeway/publish", published="0")
    assert r.status_code == 302
    assert tour(app, "giants-causeway")["published"] is False
    post(logged_in, "/admin/tours/giants-causeway/publish", published="0")   # idempotent
    assert tour(app, "giants-causeway")["published"] is False
    assert "Hidden" in logged_in.get("/admin/tours").get_data(as_text=True)
    assert "Giant&#39;s Causeway" not in logged_in.get("/tours.html").get_data(as_text=True)
    post(logged_in, "/admin/tours/giants-causeway/publish", published="1")
    assert tour(app, "giants-causeway")["published"] is True


def test_slug_change_redirects(logged_in, app):
    d = full(app, "rock-of-cashel", slug="cashel")
    assert post(logged_in, "/admin/tours/rock-of-cashel", **d).status_code == 302
    r = logged_in.get("/tours/rock-of-cashel.html")
    assert r.status_code == 301 and r.headers["Location"].endswith("/tours/cashel.html")
    assert logged_in.get("/tours/cashel.html").status_code == 200
    blog = logged_in.get("/blog/best-day-trips-from-dublin.html").get_data(as_text=True)
    assert "tours/cashel.html" in blog and "tours/rock-of-cashel.html" not in blog


def test_slug_change_with_other_fields(logged_in, app):
    d = full(app, "rock-of-cashel", slug="cashel", name="Cashel Day")
    post(logged_in, "/admin/tours/rock-of-cashel", **d)
    t = tour(app, "cashel")
    assert t and t["name"] == "Cashel Day"
    assert pub(app).content()["redirects"]["rock-of-cashel"] == "cashel"


def test_delete_blocked_when_blog_links(logged_in, app):
    h = logged_in.get("/admin/tours/cliffs-of-moher/delete").get_data(as_text=True)
    assert "Can't delete" in h and "Hide" in h
    r = post(logged_in, "/admin/tours/cliffs-of-moher/delete")
    assert r.status_code == 200 and b"Hide" in r.data
    assert tour(app, "cliffs-of-moher")


def test_delete_unlinked_tour(logged_in, app):
    slug = "meath-boyne-pub-trail"
    assert "Delete" in logged_in.get(f"/admin/tours/{slug}/delete").get_data(as_text=True)
    assert tour(app, slug)
    pub(app).apply(lambda v: {"redirects": {"old-boyne": slug}})
    r = post(logged_in, f"/admin/tours/{slug}/delete")
    assert r.status_code == 302
    assert tour(app, slug) is None
    assert logged_in.get(f"/tours/{slug}.html").status_code == 404
    assert "old-boyne" not in pub(app).content()["redirects"]


def test_multi_day_plan_must_match_days(logged_in, app):
    r = post(logged_in, "/admin/multi-day/new", name="Three Days", slug="three-days",
             days="3", summary="s", plan="one\ntwo")
    assert r.status_code == 200
    assert b"You have 3 days but 2 day descriptions" in r.data
    assert not any(m["slug"] == "three-days" for m in pub(app).content()["multi_day"])
    r = post(logged_in, "/admin/multi-day/new", name="Three Days", slug="three-days",
             days="3", summary="s", plan="one\ntwo\nthree")
    assert r.status_code == 302
    assert "Three Days" in logged_in.get("/multi-day-tours.html").get_data(as_text=True)


def test_multi_day_edit_delete_and_stale(logged_in, app):
    slug = "west-coast-explorer"
    m = next(m for m in pub(app).content()["multi_day"] if m["slug"] == slug)
    from server.admin.tours import multi_orig_values, multi_shown
    sv = multi_shown(m)
    d = dict(sv)
    d.update({"o__" + k: v for k, v in multi_orig_values(sv).items()})
    pub(app).apply(lambda v: {"multi_day": [dict(x, summary="NEW SUMMARY") if x["slug"] == slug else x
                                           for x in v["multi_day"]]})
    d["name"] = "West Coast X"
    assert post(logged_in, f"/admin/multi-day/{slug}", **d).status_code == 302
    m = next(m for m in pub(app).content()["multi_day"] if m["slug"] == slug)
    assert m["name"] == "West Coast X" and m["summary"] == "NEW SUMMARY"
    assert logged_in.get(f"/admin/multi-day/{slug}/delete").status_code == 200
    assert post(logged_in, f"/admin/multi-day/{slug}/delete").status_code == 302
    assert not any(x["slug"] == slug for x in pub(app).content()["multi_day"])


def test_multi_day_validation(logged_in):
    for kw in (dict(days="0"), dict(days="22"), dict(days="x"), dict(slug="Bad Slug"),
               dict(slug="west-coast-explorer")):
        d = dict(name="N", slug="ok-slug", days="1", summary="s", plan="a")
        d.update(kw)
        r = post(logged_in, "/admin/multi-day/new", **d)
        assert r.status_code == 200, kw


def test_tour_photo_pick(logged_in, app):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(buf, "JPEG")
    p = app.extensions["publisher"].store.add_photo(buf.getvalue(), "image/jpeg", 8, 8, "t.jpg")
    h = logged_in.get("/admin/tours/giants-causeway").get_data(as_text=True)
    assert f"/admin/photos/{p['id']}/raw" in h and "No photo" in h
    d = full(app, "giants-causeway", photo=p["id"])
    assert post(logged_in, "/admin/tours/giants-causeway", **d).status_code == 302
    assert tour(app, "giants-causeway")["photo"] == p["id"]
    assert "uploads/" in logged_in.get("/tours/giants-causeway.html").get_data(as_text=True)
    d = full(app, "giants-causeway", photo="nope")
    d["o__photo"] = "x"
    assert post(logged_in, "/admin/tours/giants-causeway", **d).status_code == 200


def test_requires_login(client):
    assert client.get("/admin/tours").status_code == 302
    assert client.get("/admin/multi-day").status_code == 302
