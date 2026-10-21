import io
import re

from PIL import Image

from tests.conftest import csrf_of


def pub(app):
    return app.extensions["publisher"]


def img(color=(200, 30, 30), size=(60, 40), fmt="JPEG"):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


def upload(c, files, **kw):
    data = {"csrf": csrf_of(c), "files": [(io.BytesIO(b), n) for n, b in files]}
    data.update(kw)
    return c.post("/admin/photos", data=data, content_type="multipart/form-data")


def photos(app):
    return pub(app).store.list_photos()


def test_page_has_phone_upload_form(logged_in):
    h = logged_in.get("/admin/photos").get_data(as_text=True)
    assert 'type="file"' in h and 'name="files"' in h and 'accept="image/*"' in h and "multiple" in h
    assert "None (use original)" in h and "Homepage hero" in h and "Taxi photo" in h and "Logo" in h


def test_upload_batch_reports_skipped_and_does_not_publish(logged_in, app):
    before = pub(app).current_dir()
    r = upload(logged_in, [("a.jpg", img()), ("b.jpg", img((1, 2, 3))), ("c.png", img(fmt="PNG")),
                           ("bad.jpg", b"garbage")], )
    assert r.status_code == 302
    h = logged_in.get("/admin/photos").get_data(as_text=True)
    assert "3 uploaded, 1 skipped: bad.jpg: That file isn&#39;t a photo we can use" in h
    assert len(photos(app)) == 3
    assert pub(app).current_dir() == before


def test_upload_nothing_selected(logged_in):
    r = upload(logged_in, [])
    assert r.status_code == 302
    assert "Choose" in logged_in.get("/admin/photos").get_data(as_text=True)


def test_upload_all_bad_never_500(logged_in, app):
    r = upload(logged_in, [("x.jpg", b"\xff\xd8\xff"), ("y.heic", b"")])
    assert r.status_code == 302 and photos(app) == []


def test_too_big_is_friendly(logged_in):
    r = upload(logged_in, [("big.jpg", b"0" * (26 * 1024 * 1024))])
    assert r.status_code == 413
    assert "Photo too big (max 25 MB)" in r.get_data(as_text=True)


def test_raw_requires_login(client, app):
    p = pub(app).store.add_photo(img(), "image/jpeg", 60, 40, "a.jpg")
    r = client.get(f"/admin/photos/{p['id']}/raw")
    assert r.status_code == 302 and "/admin/login" in r.headers["Location"]


def test_raw_serves_with_headers_and_404(logged_in, app):
    p = pub(app).store.add_photo(img(), "image/jpeg", 60, 40, "a.jpg")
    r = logged_in.get(f"/admin/photos/{p['id']}/raw")
    assert r.status_code == 200 and r.mimetype == "image/jpeg"
    assert r.headers["Cache-Control"] == "private, max-age=3600"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Content-Disposition"] == "inline"
    assert Image.open(io.BytesIO(r.data)).size == (60, 40)
    assert logged_in.get("/admin/photos/nope/raw").status_code == 404


def assign(c, **slots):
    d = {"csrf": csrf_of(c)}
    d.update(slots)
    return c.post("/admin/photos/slots", data=d)


def test_assign_hero_slot_live(logged_in, app):
    upload(logged_in, [("a.jpg", img())])
    p = photos(app)[0]
    r = assign(logged_in, slot_hero=p["id"], slot_taxi="", slot_logo="",
               o__slot_hero="", o__slot_taxi="", o__slot_logo="")
    assert r.status_code == 302
    assert pub(app).content()["photo_slots"]["hero"] == p["id"]
    home = logged_in.get("/").get_data(as_text=True)
    m = re.search(r"uploads/[0-9a-f]{12}\.jpg", home)
    assert m and p["sha"][:12] in m.group(0)
    r = logged_in.get("/" + m.group(0))
    assert r.status_code == 200 and r.headers["Cache-Control"] == "public, max-age=604800"


def test_assign_only_changed_slots_and_none(logged_in, app):
    upload(logged_in, [("a.jpg", img()), ("b.jpg", img((9, 9, 9)))])
    a, b = photos(app)
    assign(logged_in, slot_hero=a["id"], slot_taxi="", slot_logo="",
           o__slot_hero="", o__slot_taxi="", o__slot_logo="")
    # stale tab: it thinks hero was empty; it only changes taxi -> hero must survive
    assign(logged_in, slot_hero="", slot_taxi=b["id"], slot_logo="",
           o__slot_hero="", o__slot_taxi="", o__slot_logo="")
    s = pub(app).content()["photo_slots"]
    assert s["hero"] == a["id"] and s["taxi"] == b["id"]
    assign(logged_in, slot_hero="", slot_taxi=b["id"], slot_logo="",
           o__slot_hero=a["id"], o__slot_taxi=b["id"], o__slot_logo="")
    assert pub(app).content()["photo_slots"]["hero"] is None


def test_assign_unknown_photo_rejected(logged_in, app):
    r = assign(logged_in, slot_hero="nope", o__slot_hero="")
    assert r.status_code == 200 and "doesn&#39;t exist" in r.get_data(as_text=True)
    assert pub(app).content()["photo_slots"]["hero"] is None


def test_delete_in_use_refused(logged_in, app):
    upload(logged_in, [("a.jpg", img())])
    p = photos(app)[0]
    assign(logged_in, slot_hero=p["id"], o__slot_hero="")
    pub(app).apply(lambda v: {"tours": [dict(t, photo=p["id"]) if t["slug"] == "giants-causeway"
                                        else t for t in v["tours"]]})
    h = logged_in.get("/admin/photos").get_data(as_text=True)
    assert "Used by: Homepage hero, " in h
    r = logged_in.post(f"/admin/photos/{p['id']}/delete", data={"csrf": csrf_of(logged_in)})
    assert r.status_code == 200
    t = r.get_data(as_text=True)
    assert "Used by: Homepage hero, Giant&#39;s Causeway" in t
    assert len(photos(app)) == 1


def test_delete_in_use_by_hidden_tour(logged_in, app):
    upload(logged_in, [("a.jpg", img())])
    p = photos(app)[0]
    pub(app).apply(lambda v: {"tours": [dict(t, photo=p["id"], published=False)
                                        if t["slug"] == "giants-causeway" else t
                                        for t in v["tours"]]})
    r = logged_in.post(f"/admin/photos/{p['id']}/delete", data={"csrf": csrf_of(logged_in)})
    assert "Used by:" in r.get_data(as_text=True) and len(photos(app)) == 1


def test_delete_unused_confirms_then_removes_from_release(logged_in, app):
    upload(logged_in, [("a.jpg", img())])
    p = photos(app)[0]
    g = logged_in.get(f"/admin/photos/{p['id']}/delete")
    assert g.status_code == 200 and "Yes, delete" in g.get_data(as_text=True)
    assert len(photos(app)) == 1
    r = logged_in.post(f"/admin/photos/{p['id']}/delete", data={"csrf": csrf_of(logged_in)})
    assert r.status_code == 302 and photos(app) == []
    root = pub(app).current_dir()
    assert not list((root / "uploads").glob("*")) if (root / "uploads").exists() else True
    assert logged_in.get(f"/admin/photos/{p['id']}/delete").status_code == 404


def test_photos_requires_login(client):
    assert client.get("/admin/photos").status_code == 302
    assert client.post("/admin/photos/slots").status_code in (302, 400)


def test_raw_refuses_non_image_mime(logged_in, app):
    p = pub(app).store.add_photo(b"<svg onload=alert(1)>", "image/svg+xml", 1, 1, "x.svg")
    assert logged_in.get(f"/admin/photos/{p['id']}/raw").status_code == 404
    q = pub(app).store.add_photo(b"<html>", "text/html", 1, 1, "y.html")
    assert logged_in.get(f"/admin/photos/{q['id']}/raw").status_code == 404


def test_delete_already_deleted_redirects_with_flash(logged_in, app):
    upload(logged_in, [("a.jpg", img())])
    pid = photos(app)[0]["id"]
    tok = csrf_of(logged_in)
    assert logged_in.post(f"/admin/photos/{pid}/delete", data={"csrf": tok}).status_code == 302
    r = logged_in.post(f"/admin/photos/{pid}/delete", data={"csrf": csrf_of(logged_in)})
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/photos")
    assert "already deleted" in logged_in.get("/admin/photos").get_data(as_text=True)
