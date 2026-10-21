import time

from tests.conftest import csrf_of


def post(c, url, data):
    return c.post(url, data={"csrf": csrf_of(c), **data})


def base_prices(app, **over):
    """A valid prices form built from the live content."""
    c = app.extensions["publisher"].content()
    d = {k: str(c["settings"][k]) for k in
         ("multi_day_rate", "extra_hour_rate", "max_passengers")}
    for t in c["tours"]:
        d[f"tour_price__{t['slug']}"] = "" if t["price"] is None else str(t["price"])
    for i, f in enumerate(c["airport_fares"]):
        d.update({f"fare-{i}-area": f["area"], f"fare-{i}-distance": f["distance"],
                  f"fare-{i}-to": str(f["to"]), f"fare-{i}-from": str(f["from"])})
    for i, f in enumerate(c["long_transfers"]):
        d.update({f"long-{i}-area": f["area"], f"long-{i}-price": str(f["price"])})
    d.update(over)
    return d


def test_prices_update_live(app, logged_in):
    r = post(logged_in, "/admin/prices", base_prices(app, **{"tour_price__ring-of-kerry": "499"}))
    assert r.status_code == 302 and r.headers["Location"] == "/admin/prices"
    assert "Saved. The site is updated." in logged_in.get("/admin/prices").get_data(as_text=True)
    assert "€499" in logged_in.get("/tours/ring-of-kerry.html").get_data(as_text=True)


def test_price_blank_means_on_request(app, logged_in):
    post(logged_in, "/admin/prices", base_prices(app, **{"tour_price__ring-of-kerry": "  "}))
    tours = {t["slug"]: t for t in app.extensions["publisher"].content()["tours"]}
    assert tours["ring-of-kerry"]["price"] is None
    assert "Price on request" in logged_in.get("/tours/ring-of-kerry.html").get_data(as_text=True)


def test_price_formats(app, logged_in):
    for raw, ok in (("€450", True), (" 450.00 ", True), ("450.50", False), ("4,50", False),
                    ("abc", False), ("-5", False), ("100001", False)):
        r = post(logged_in, "/admin/prices",
                 base_prices(app, **{"tour_price__ring-of-kerry": raw}))
        assert (r.status_code == 302) == ok, raw
        if not ok:
            assert r.status_code == 200 and raw.strip().encode() in r.data


def test_prices_ignore_deleted_slug(app, logged_in):
    r = post(logged_in, "/admin/prices", base_prices(app, **{"tour_price__gone-tour": "123"}))
    assert r.status_code == 302


def test_add_and_remove_airport_fare(app, logged_in):
    page = logged_in.get("/admin/prices").get_data(as_text=True)
    n = len(app.extensions["publisher"].content()["airport_fares"])
    assert f'name="fare-{n + 1}-area"' in page and f'name="fare-{n + 2}-area"' not in page
    d = base_prices(app, **{f"fare-{n}-area": "Swords", f"fare-{n}-to": "€30",
                            f"fare-{n}-from": "35", "fare-0-remove": "on"})
    assert post(logged_in, "/admin/prices", d).status_code == 302
    fares = app.extensions["publisher"].content()["airport_fares"]
    assert fares[-1] == {"area": "Swords", "distance": "", "to": 30, "from": 35}
    assert len(fares) == n  # one added, one removed


def test_fare_row_needs_prices_and_blank_ignored(app, logged_in):
    n = len(app.extensions["publisher"].content()["airport_fares"])
    r = post(logged_in, "/admin/prices", base_prices(app, **{f"fare-{n}-area": "Swords"}))
    assert r.status_code == 200 and b"price to airport" in r.data
    r = post(logged_in, "/admin/prices", base_prices(app, **{f"fare-{n}-area": " "}))
    assert r.status_code == 302


def test_long_transfer_add_remove(app, logged_in):
    d = base_prices(app, **{"long-0-remove": "on", "long-5-area": "Belfast",
                            "long-5-price": "320"})
    assert post(logged_in, "/admin/prices", d).status_code == 302
    longs = app.extensions["publisher"].content()["long_transfers"]
    assert {"area": "Belfast", "price": 320} in longs and len(longs) == 2


def test_prices_validation_rerenders_with_values(app, store, logged_in):
    before = store.load()
    r = post(logged_in, "/admin/prices", base_prices(app, multi_day_rate="abc"))
    assert r.status_code == 200
    assert b"Multi-day rate" in r.data and b'value="abc"' in r.data
    assert store.load() == before


def test_max_passengers_range(app, logged_in):
    assert post(logged_in, "/admin/prices", base_prices(app, max_passengers="21")).status_code == 200
    assert post(logged_in, "/admin/prices", base_prices(app, max_passengers="0")).status_code == 200
    assert post(logged_in, "/admin/prices", base_prices(app, max_passengers="8")).status_code == 302


def test_build_error_rerenders_200(app, store, logged_in, monkeypatch):
    from build import BuildError
    pub = app.extensions["publisher"]
    def boom(*a, **k):
        raise BuildError(["a.html -> missing.html", "b", "c", "d"])
    monkeypatch.setattr("server.publish.build_site", boom)
    before = store.load()
    r = post(logged_in, "/admin/prices", base_prices(app, multi_day_rate="700"))
    assert r.status_code == 200
    assert b"Couldn&#39;t publish: a.html -&gt; missing.html; b; c" in r.data
    assert b"Nothing was changed." in r.data and b'value="700"' in r.data
    assert store.load() == before


def contact_form(**over):
    d = {"phone": "+353 87 033 0046", "phone_display": "087 033 0046",
         "email": "old@example.com", "whatsapp_number": "353870330046"}
    d.update(over)
    return d


def test_email_change_sets_banner_and_config(app, logged_in):
    r = post(logged_in, "/admin/contact", contact_form(email="new@example.com"))
    assert r.status_code == 302
    c = app.extensions["publisher"].content()
    assert c["settings"]["email"] == "new@example.com"
    assert c["flags"]["email_unconfirmed"] == "new@example.com"
    for url in ("/admin/", "/admin/contact"):
        html = logged_in.get(url).get_data(as_text=True)
        assert "Booking forms now send to new@example.com." in html
        assert "<strong>Bookings will not arrive until you confirm it:</strong>" in html
        assert "I've confirmed it" in html
    assert "new@example.com" in (app.extensions["publisher"].current_dir()
                                 / "js" / "config.js").read_text()


def test_unchanged_email_sets_no_banner(app, logged_in):
    pub = app.extensions["publisher"]
    cur = pub.content()["settings"]
    # phone-only edit: no flag
    post(logged_in, "/admin/contact", contact_form(email=cur["email"], phone_display="087 111 2222"))
    assert "email_unconfirmed" not in pub.content()["flags"]
    # case-only change is not a change
    post(logged_in, "/admin/contact", contact_form(email=cur["email"].upper()))
    assert "email_unconfirmed" not in pub.content()["flags"]
    # a real change sets it, and confirming clears it again
    post(logged_in, "/admin/contact", contact_form(email="other@example.com"))
    assert pub.content()["flags"]["email_unconfirmed"] == "other@example.com"
    post(logged_in, "/admin/contact/confirm", {})
    assert "email_unconfirmed" not in pub.content()["flags"]
    # saving other fields with the (now current) email keeps it clear
    post(logged_in, "/admin/contact", contact_form(email="other@example.com", phone_display="1 2 3 4 5 6 7"))
    assert "email_unconfirmed" not in pub.content()["flags"]


def test_confirm_clears_banner(app, logged_in):
    post(logged_in, "/admin/contact", contact_form(email="new@example.com"))
    r = post(logged_in, "/admin/contact/confirm", {})
    assert r.status_code == 302 and r.headers["Location"] == "/admin/"
    assert "email_unconfirmed" not in app.extensions["publisher"].content()["flags"]
    assert b"email-unconfirmed" not in logged_in.get("/admin/").data


def test_contact_validation(app, store, logged_in):
    before = store.load()
    for field, bad in (("email", "nope"), ("phone", "abc"), ("whatsapp_number", "+353 87"),
                       ("phone_display", " ")):
        r = post(logged_in, "/admin/contact", contact_form(**{field: bad}))
        assert r.status_code == 200 and b"flash err" in r.data, field
    assert store.load() == before


def test_confirm_requires_login_and_csrf(client, logged_in):
    assert client.post("/admin/contact/confirm").status_code == 400


def test_text_override_and_reset(app, logged_in):
    from texts import all_text_defaults
    key, meta = next((k, m) for k, m in all_text_defaults().items() if k == "home.hero_title")
    r = post(logged_in, "/admin/text", {f"t__{key}": "Zebra Taxis Ireland"})
    assert r.status_code == 302
    assert app.extensions["publisher"].content()["texts"] == {key: "Zebra Taxis Ireland"}
    assert "Zebra Taxis Ireland" in logged_in.get("/").get_data(as_text=True)
    r = post(logged_in, "/admin/text", {f"t__{key}": "Zebra Taxis Ireland", f"reset__{key}": "on"})
    assert r.status_code == 302
    assert app.extensions["publisher"].content()["texts"] == {}
    assert meta["default"] in logged_in.get("/").get_data(as_text=True)


def test_text_unchanged_not_stored(app, logged_in):
    from texts import all_text_defaults
    form = {f"t__{k}": m["default"] for k, m in all_text_defaults().items()}
    assert post(logged_in, "/admin/text", form).status_code == 302
    assert app.extensions["publisher"].content()["texts"] == {}


def test_text_empty_rejected_and_group_open(app, store, logged_in):
    before = store.load()
    r = post(logged_in, "/admin/text", {"t__home.hero_title": "   ", "t__bogus.key": "x"})
    assert r.status_code == 200 and b"Hero title can&#39;t be empty" in r.data
    assert b'<details class="card" open>' in r.data
    assert r.data.count(b"<details class=\"card\" open>") == 1
    assert store.load() == before


def test_text_unknown_key_ignored_and_page_fast(app, logged_in):
    assert post(logged_in, "/admin/text", {"t__bogus.key": "x"}).status_code == 302
    assert app.extensions["publisher"].content()["texts"] == {}
    t = time.time()
    r = logged_in.get("/admin/text")
    assert r.status_code == 200 and time.time() - t < 1.0
    assert b"<details" in r.data and b"open>" not in r.data


def test_huge_and_unicode_numbers_rejected(app, logged_in):
    for raw in ("9" * 5000, "٤٥٠", "1" * 10):
        r = post(logged_in, "/admin/prices", base_prices(app, multi_day_rate=raw))
        assert r.status_code == 200 and b"flash err" in r.data, raw[:10]
    r = post(logged_in, "/admin/prices", base_prices(app, **{"tour_price__ring-of-kerry": "9" * 5000}))
    assert r.status_code == 200 and b"too long" in r.data
    r = post(logged_in, "/admin/prices", base_prices(app, **{"tour_price__ring-of-kerry": "9" * 150}))
    assert r.status_code == 200 and b"between" in r.data


def test_length_caps(app, logged_in):
    r = post(logged_in, "/admin/contact", contact_form(phone_display="x" * 201))
    assert r.status_code == 200 and b"too long" in r.data
    r = post(logged_in, "/admin/text", {"t__home.hero_title": "x" * 2001})
    assert r.status_code == 200 and b"too long" in r.data
    assert b'maxlength="2000"' in logged_in.get("/admin/text").data


def _form_of(client, url):
    """Parse a rendered admin form into a dict, as a browser would submit it."""
    import re
    from html import unescape
    html = client.get(url).get_data(as_text=True)
    out = {}
    for m in re.finditer(r'<input[^>]*name="([^"]+)"[^>]*?(?:value="([^"]*)")?[^>]*>', html):
        tag = m.group(0)
        if 'type="checkbox"' in tag or 'name="csrf"' in tag:
            continue
        v = re.search(r'value="([^"]*)"', tag)
        out[m.group(1)] = unescape(v.group(1)) if v else ""
    for m in re.finditer(r'<textarea[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>', html, re.S):
        out[m.group(1)] = unescape(m.group(2)).lstrip("\n")
    return out


def test_text_stale_tab_keeps_newer_edit(app, logged_in):
    stale = _form_of(logged_in, "/admin/text")
    assert post(logged_in, "/admin/text", {"t__home.hero_title": "Newer title"}).status_code == 302
    stale["t__home.hero_title_gold"] = "Gold from the stale tab"
    assert post(logged_in, "/admin/text", stale).status_code == 302
    assert app.extensions["publisher"].content()["texts"] == {
        "home.hero_title": "Newer title", "home.hero_title_gold": "Gold from the stale tab"}


def test_prices_stale_tab_keeps_newer_price(app, logged_in):
    stale = _form_of(logged_in, "/admin/prices")
    assert post(logged_in, "/admin/prices", base_prices(app, **{"tour_price__ring-of-kerry": "777"})).status_code == 302
    stale["extra_hour_rate"] = "55"
    assert post(logged_in, "/admin/prices", stale).status_code == 302
    c = app.extensions["publisher"].content()
    assert {t["slug"]: t["price"] for t in c["tours"]}["ring-of-kerry"] == 777
    assert c["settings"]["extra_hour_rate"] == 55


def test_fares_stale_tab_rejected(app, store, logged_in):
    stale = _form_of(logged_in, "/admin/prices")
    n = len(app.extensions["publisher"].content()["airport_fares"])
    other = base_prices(app, **{f"fare-{n}-area": "Swords", f"fare-{n}-to": "30", f"fare-{n}-from": "35"})
    assert post(logged_in, "/admin/prices", other).status_code == 302
    # untouched lists + unrelated edit: newer fare survives
    stale["multi_day_rate"] = "700"
    assert post(logged_in, "/admin/prices", stale).status_code == 302
    c = app.extensions["publisher"].content()
    assert c["settings"]["multi_day_rate"] == 700 and c["airport_fares"][-1]["area"] == "Swords"
    # touching the list from a stale form is rejected
    stale2 = _form_of(logged_in, "/admin/prices")
    assert post(logged_in, "/admin/prices", base_prices(app, **{"fare-0-remove": "on"})).status_code == 302
    before = store.load()
    stale2["fare-1-to"] = "99"
    r = post(logged_in, "/admin/prices", stale2)
    assert r.status_code == 200 and b"changed in another tab" in r.data
    assert store.load() == before


def test_prices_error_rerender_offers_blank_rows(app, logged_in):
    n = len(app.extensions["publisher"].content()["airport_fares"])
    r = post(logged_in, "/admin/prices", base_prices(app, multi_day_rate="abc"))
    assert f'name="fare-{n + 1}-area"' in r.get_data(as_text=True)
    assert f'name="fare-{n + 2}-area"' not in r.get_data(as_text=True)


def test_script_in_text_value_escaped_on_admin_page(app, logged_in):
    payload = "<script>alert(1)</script>"
    post(logged_in, "/admin/text", {"t__home.hero_title": payload})
    html = logged_in.get("/admin/text").get_data(as_text=True)
    assert payload not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html
