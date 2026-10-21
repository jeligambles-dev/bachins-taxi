# BCH Taxi Admin + Pub Tours + Golf Trips Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The owner edits prices, tours (including new Rural Pub Tours and Golf Trips), photos, page text and contact details from a phone-friendly `/admin`, and the live site updates within seconds.

**Architecture:** One Flask app (gunicorn, 1 worker, threads) replaces Caddy. It serves the generated static site from `SITE_ROOT/current` (a symlink to the newest release) and the admin UI. Content is stored in Railway Postgres as **owner overrides only**, one row per section. At build time those overrides are merged over defaults that live in code (`build/data.py`, `build/texts.py`, the index template), so new code defaults never get lost. Every save runs the existing Python generator, refactored to `build_site(content, out_dir)`, into a fresh release directory. The DB is committed and the symlink swapped only if the build succeeds. On boot the server builds from the DB before reporting healthy.

**Tech Stack:** Python 3.14, Flask, gunicorn, psycopg 3 (`psycopg[binary]`), Pillow + pillow-heif, Jinja2 (via Flask) for admin templates, pytest against a real local Postgres.

**Spec:** `docs/superpowers/specs/2026-10-22-admin-and-new-tours-design.md`

## Global Constraints

- Python 3.14 locally and in Docker (`python:3.14-slim`). Pin exact versions in `requirements.txt`.
- No JS framework in the admin. Use server-rendered forms that work without JS. Small progressive JS is fine. Never use `alert()`/`confirm()`; destructive actions get a confirmation page.
- The admin is phone-first: usable at 375 px wide, tap targets ≥ 44 px, one column, no horizontal scroll.
- Prices are whole euros (int ≥ 0) or unset. An unset price renders as **"Price on request"**, never "€0", "€X" or "€None".
- Golf trips have one fixed price per trip (label "per trip"). Day and pub tours are "per vehicle".
- Every owner-entered string is HTML-escaped on output (`html.escape` in the generator, Jinja autoescape in admin).
- Flask serves files **only** from the active release directory and `server/static/`, never from the repo root.
- Secrets come from env: `DATABASE_URL`, `ADMIN_PASSWORD`, `SECRET_KEY`, `SITE_ROOT` (default `/tmp/bch-site`). Never commit or log them.
- Booking forms post to `https://formsubmit.co/ajax/<email from admin>`.
- Blog posts stay code-edited (`build/posts.py`). There is one admin login, with no history or undo.
- The tests need `TEST_DATABASE_URL` (local: `createdb bch_taxi_test` then `postgresql:///bch_taxi_test`).

## Review Focus

1. **Redeploy or restart**: the container disk is wiped, so the owner's edits must reappear on the first response. `/health` returns 503 until the boot build from the DB finishes (Task 9 test `test_boot_builds_from_db_before_healthy`).
2. **A price left blank anywhere**: no "€0", no "€X", no crash in the title, JSON-LD, calculator, destinations, the index meta `min()` or the booking modal (Task 3 test `test_unpriced_tour_everywhere`).
3. **Hiding, deleting or renaming any seeded tour**, including `glendalough-wicklow`, `connemara-galway` and `dingle-peninsula`, which `footer()` currently hard-codes: the build still succeeds (Task 3 `test_footer_survives_missing_hardcoded_slugs`, Task 6 `test_rename_rewrites_blog_links`).
4. **A phone photo upload**: it may be portrait with an EXIF rotation, 8–15 MB, HEIC or carry GPS EXIF. It must come out upright, resized, with no EXIF, and a new photo must never be served under an old cached filename (Task 13 `test_upload_portrait_exif_rotated`, `test_upload_strips_gps`, `test_upload_heic`, Task 5 `test_photo_filenames_are_content_hashed`).
5. **Stale tab**: saving the prices form in an old phone tab must not undo text edits made since on the computer. Each form patches only its own section, re-read under the lock (Task 8 `test_apply_patches_only_changed_sections`).

---

### Task 0: Commit the existing site and set up tooling

**Files:**
- Modify: `.gitignore` (add `dist/`, `.venv/`, `__pycache__/`, `.pytest_cache/`)
- Create: `requirements.txt`, `requirements-dev.txt` (pytest), `pytest.ini` (`testpaths = tests`)

- [ ] **Step 1:** `git status`. Commit everything currently untracked or modified that belongs to the site (`build/`, `css/`, `js/`, `blog/`, `tours/`, `*.html`, `Dockerfile`, `Caddyfile`, `.dockerignore`, `.gitignore`, `railway.json`, `robots.txt`, `sitemap.xml`, `images/`) as **its own commit**: `chore: commit current site state`.
- [ ] **Step 2:** Create the venv: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt`. Then `createdb bch_taxi_test` (ignore "already exists").
- [ ] **Step 3:** Commit tooling: `chore: python deps and pytest config`.

### Task 1: Content model, defaults and merge

**Files:**
- Create: `build/content.py`
- Modify: `build/data.py`: add `kind="day"` to every tour, and add the starter pub and golf entries (below)
- Test: `tests/test_content.py`

**Interfaces:**
- Produces:
  - `SECTIONS = ("settings", "texts", "tours", "multi_day", "airport_fares", "long_transfers", "photo_slots", "redirects", "flags")`
  - `default_content() -> dict`: built from `data.py`. `settings` = `{phone, phone_display, email, whatsapp_number, site_url, multi_day_rate, extra_hour_rate, max_passengers}`. `texts` = `{}`. `tours` = list of normalized tour dicts. `multi_day`, `airport_fares` (list of `{area, distance, to, from}`), `long_transfers` (list of `{area, price}`), `photo_slots = {"hero": None, "taxi": None, "logo": None}`, `redirects = {}`, `flags = {}`.
  - `merge(defaults: dict, stored: dict) -> dict`: `settings`, `texts`, `photo_slots`, `flags` merge per key (stored wins). The list sections and `redirects` are replaced wholesale when present in `stored`. Unknown stored keys are ignored. Every tour passes through `normalize_tour`.
  - `normalize_tour(t: dict) -> dict`: fills missing fields with defaults: `kind="day"`, `published=True`, `fav=False`, `price=None`, `photo=None`, `area=""`, `drive=""`, `highlights=[]`, `intro=""`, `desc=""`, `duration=""`, `region=""`.
  - `KINDS = {"day": "Day tour", "pub": "Rural pub tour", "golf": "Golf trip"}`
  - `price_label(t) -> str` returns `"€1,234"` or `"Price on request"`. `price_unit(t) -> str` returns `"per trip"` for golf, else `"per vehicle"`.
  - `validate_tour(t: dict, others: list[dict]) -> list[str]` returns error messages in plain English:
    - slug must match `^[a-z0-9]+(-[a-z0-9]+)*$` and be unique among `others`
    - name must not be empty
    - kind must be in `KINDS`
    - price must be None or an int from 0 to 100000
  - `ValidationError(Exception)` with `.errors: list[str]`.

Starter entries in `data.py` (prices `None`; write fresh copy in the site's voice, with 4–6 highlights each):
- pub: `meath-boyne-pub-trail` "Boyne Valley Pub Trail"; `wicklow-country-pubs` "Wicklow Country Pubs & Trad Music"
- golf: `dublin-links-golf-day` "Dublin Links Golf Day"; `south-west-links-golf-trip` "South-West Links Golf Trip" (duration "3 days")

- [ ] **Step 1: Write failing tests**
  - `test_default_content_has_all_sections`: `set(default_content()) == set(SECTIONS)`.
  - `test_seeded_day_tours_unchanged`: there are 12 tours with kind `day`, and `ring-of-kerry` has price 460.
  - `test_starter_pub_and_golf_unpriced`: the 4 starter slugs exist with `price is None`.
  - `test_merge_settings_per_key`: stored `{"settings": {"email": "a@b.ie"}}` → email overridden, phone still the default.
  - `test_merge_new_default_text_key_survives`: defaults texts `{"x": "1", "y": "2"}`, stored `{"texts": {"x": "9"}}` → `{"x": "9", "y": "2"}`.
  - `test_merge_tours_replaced_and_normalized`: stored tours `[{"slug": "a", "name": "A"}]` → one tour, `published is True`, `kind == "day"`.
  - `test_price_label`: `None` → `"Price on request"`; `1234` → `"€1,234"`.
  - `test_validate_tour_errors`: covers a bad slug, a duplicate slug, a blank name, price `-1`, and price `"abc"`. Each yields ≥ 1 message.
- [ ] **Step 2:** Run `.venv/bin/pytest tests/test_content.py -v`. Expect FAIL (module missing).
- [ ] **Step 3:** Implement `build/content.py` and the `data.py` additions.
- [ ] **Step 4:** Re-run. Expect PASS.
- [ ] **Step 5:** Commit: `feat: content model with defaults and override merge`.

### Task 2: Refactor the generator to `build_site(content, out_dir)` (no visible change)

**Files:**
- Move: `index.html` → `build/templates/index.html`. This is now the template, and nothing ever writes to it.
- Modify: `build/build.py`
- Delete from git: the generated outputs `index.html`, `tours.html`, `tours/`, `multi-day-tours.html`, `price-calculator.html`, `destinations.html`, `blog.html`, `blog/`, `sitemap.xml`, `robots.txt`. They are now build products in `dist/`.
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: `default_content`, `merge` (Task 1)
- Produces:
  - `build_site(content: dict, out_dir: Path) -> None`: copies `css/`, `js/` and `images/` into `out_dir`, writes every page and `index.html` into `out_dir`, then runs `check_links` on `out_dir`. Raises `BuildError(broken: list[str])` on broken links.
  - CLI: `python3 build/build.py [--out DIR]` (default `dist/`) builds `merge(default_content(), {})`.
  - Internally, replace `from data import *` globals with a module-level context set by `build_site`, for example a `_C` dict holding the content plus derived `PHONE`, `WHATSAPP` and so on. Every builder reads from it.

- [ ] **Step 1: Write failing tests**
  - `test_build_site_writes_pages(tmp_path)`: after building default content, `index.html`, `tours/ring-of-kerry.html`, `price-calculator.html` and `css/style.css` exist in `tmp_path`.
  - `test_template_never_modified(tmp_path)`: the sha256 of `build/templates/index.html` is unchanged after `build_site`.
  - `test_build_error_on_broken_link(tmp_path)`: monkeypatch the first post in `build.POSTS` so its body contains `<a href="{ROOT}tours/nope.html">x</a>`, then expect `BuildError` whose `.broken` mentions `tours/nope.html`.
- [ ] **Step 2:** Run. Expect FAIL.
- [ ] **Step 3:** Refactor `build.py`. Before Step 1 of Task 3 changes the defaults, temporarily build with only the 12 day tours.
- [ ] **Step 4: Parity check (one-off, not a test).** Build only the 12 day tours (filter `kind=="day"` for this check) and compare against the committed output:
  - `git worktree add /tmp/bch-old HEAD`
  - `python3 build/build.py --out /tmp/bch-parity`
  - `diff -r` every generated HTML file, plus `sitemap.xml`, between `/tmp/bch-old` and `/tmp/bch-parity`

  Expected: no differences. Fix any diff, then `git worktree remove /tmp/bch-old`.
- [ ] **Step 5:** Run all tests. Expect PASS. Commit: `refactor: generator builds from content dict into an output dir`.

### Task 3: Tour kinds, hidden tours, "Price on request", new listing pages

**Files:**
- Modify: `build/build.py`, `build/templates/index.html` (service dropdowns), `build/partials/modal.html` if it has a service list, `js/main.js` (modal price)
- Test: `tests/test_build_tours.py`

**Interfaces:**
- Consumes: `price_label`, `price_unit`, `KINDS`
- Produces: pages `pub-tours.html` and `golf-trips.html`. Detail pages for every kind live at `tours/<slug>.html`. Helper `published(kind=None) -> list[dict]`.

Behaviour:
- **Listings:**
  - `tours.html`, `destinations.html` and the calculator show published `day` tours only.
  - `pub-tours.html` and `golf-trips.html` show their kind. Each has a hero, the cards, a short "what's included" block and `cta_band`.
  - The homepage tours grid shows all published tours, day first, then pub, then golf.
- **Nav:** add "Pub Tours" and "Golf" after "Tours", with active keys `pub` and `golf`. Add them to the footer "Explore" list too.
- **Footer "Popular Tours":** published `fav` tours, then other published day tours, up to 6. No hard-coded slugs.
- **Hidden** (`published=False`): the detail page is still built, with `<meta name="robots" content="noindex">`. The tour is left out of every listing, the homepage grid, the footer, "You might also like", the calculator, destinations and the sitemap.
- **Detail page per kind:**
  - The h1 suffix is "Private Tour", "Rural Pub Tour" or "Golf Trip", and the crumb points to its listing page.
  - The included list and the good-to-know paragraph come from text keys per kind (Task 4 makes them editable; define the defaults here). Pub tours: "Your driver gets everyone home safely". Golf: "Room for clubs and bags".
  - The "Add extras in the price calculator" link appears for day tours only.
- **Unpriced tour:**
  - `data-price=""`.
  - The card, book card and destinations show `price_label`.
  - The `<title>` drops the `| €X per Vehicle` part, and the meta description drops "from €X".
  - JSON-LD omits `offers`.
  - The calculator omits the tour.
  - The index meta regex uses `min()` over priced published day tours and leaves the text untouched if there are none.
  - `main.js` modal: when `data-price` is empty, show "Price on request" in `tm-sub`, the summary total and the `tourExtra` "Price" line.
- **Counts:** the tours hub lead and meta description no longer hard-code "Twelve" or "12". Compute the count from published day tours.
- **Service dropdowns:** add `<option>Rural pub tour</option>` and `<option>Golf trip</option>` to `#qb-service` and `#cf-service`. Detail-page "Book" for pub and golf uses the same modal as tours.

- [ ] **Step 1: Write failing tests** (each builds `merge(default_content(), stored)` into `tmp_path`)
  - `test_pub_and_golf_listing_pages`: `pub-tours.html` contains "Boyne Valley Pub Trail", and `golf-trips.html` contains "Dublin Links Golf Day".
  - `test_unpriced_tour_everywhere`: with the starter tours unpriced and `ring-of-kerry` set to `price=None`:
    - no output file contains `€0`, `€None` or `€X`
    - the `ring-of-kerry` page title has no `€`
    - its JSON-LD has no `"offers"`
    - the `calc-data` JSON has no `ring-of-kerry`
    - the destinations page contains "Price on request"
    - the index card's `data-price=""`
  - `test_all_tours_unpriced_builds`: every tour's price is None, and the build still succeeds.
  - `test_hidden_tour_excluded`: with `cliffs-of-moher` set to `published=False`, its page exists and contains `noindex`, while `tours.html`, `index.html`, `sitemap.xml` and the footer of `blog.html` don't mention it.
  - `test_footer_survives_missing_hardcoded_slugs`: with `glendalough-wicklow`, `connemara-galway` and `dingle-peninsula` set to `published=False`, the build succeeds and none of the three appears in any footer. They're hidden rather than removed, because blog posts link to them; Task 6 covers renames.
  - `test_golf_price_unit`: a golf tour with price 900 shows "€900" and "per trip".
  - `test_service_dropdowns_have_new_trips`: `index.html` `#cf-service` and `#qb-service` each contain "Rural pub tour" and "Golf trip".
- [ ] **Step 2:** Run. Expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run all tests. Expect PASS. Open `dist/index.html` and `dist/golf-trips.html` in a browser at 375 px and on desktop, and check the new nav items wrap correctly in the mobile menu.
- [ ] **Step 5:** Commit: `feat: pub tours, golf trips, hidden tours, price on request`.

### Task 4: Editable page text and contact details

**Files:**
- Create: `build/texts.py`
- Modify: `build/build.py`, `build/templates/index.html`, `build/partials/*.html`, `js/main.js`
- Test: `tests/test_texts.py`

**Interfaces:**
- Produces:
  - `TEXTS: dict[str, tuple[str, str, str]]` maps key → `(group, label, default)` for every string currently hard-coded in `build.py`. That covers the `cta_band` default, `group_band` copy, `INCLUDED` (one item per line) and per-kind included lists, good-to-know paragraphs, all page hero labels, h1s and leads, the multi-day pricing notes, the calculator row descriptions and the "How it works" steps, the destinations note, the footer about and CTA paragraphs, and the pub/golf listing copy.
  - Key format: `<page>.<name>`, e.g. `tours.lead`, `footer.about`. Groups are page names ("Home page", "Tours page", "Footer", …).
  - `T(key) -> str`: the escaped merged value. `T_lines(key) -> list[str]` for list texts.
  - `template_texts(template: str) -> dict[str, str]`: extracts `<!-- @t:key -->default<!-- /@t:key -->` markers. Labels for template keys come from humanizing the key; group "Home page".
  - `all_text_defaults() -> dict[str, dict]`: `{key: {"group", "label", "default", "multiline": bool}}` from both sources, for the admin.
- Template markers: wrap every visible plain-text run in `build/templates/index.html` (headings, paragraphs, list items, button labels, FAQ questions and answers) in `<!-- @t:home.<name> -->…<!-- /@t:home.<name> -->`.
  - Only plain text goes inside a marker. Keep inline markup (`<strong>`, links) outside, or split the run. Convert `&amp;` inside a marker to `&` in the default, since values are escaped on output.
  - The build replaces each marker with the escaped merged value and **strips the markers** from the output.
- Contact tokens: replace every hard-coded phone, email and WhatsApp value in the template and partials with tokens. This includes the JSON-LD (lines ~27–28, 49), the hero call button (~170), the contact cards (~755–768), the FAB, the group band and the footer.
  - The tokens are `{{PHONE}}`, `{{PHONE_DISPLAY}}`, `{{EMAIL}}` and `{{WA_NUMBER}}` (digits only), used as `https://wa.me/{{WA_NUMBER}}`.
  - In JSON-LD, insert the values JSON-escaped. In HTML, insert them HTML-escaped.
- `js/config.js` is generated per build: `window.BCH = {email, waNumber, phoneDisplay};`. Every page includes it before `main.js` as `js/config.js?v=<sha8 of its content>`.
  - `main.js` reads `FORM_ENDPOINT` and `WHATSAPP` from `window.BCH`.
  - The line-92 error message uses `window.BCH.phoneDisplay`.

- [ ] **Step 1: Write failing tests**
  - `test_text_override_on_index_and_subpage`: stored texts `{"home.hero_title": "Hello <b>", "footer.about": "About us"}` → `index.html` contains `Hello &lt;b&gt;`, and `tours.html` contains "About us".
  - `test_markers_stripped`: no output file contains `<!-- @t:`.
  - `test_every_template_marker_has_default`: `template_texts()` returns ≥ 60 keys, none with an empty default.
  - `test_default_build_text_matches_before(tmp_path)`: the built `index.html` with no overrides contains the original hero heading and FAQ text verbatim.
  - `test_contact_change_everywhere`: settings `{"email": "new@x.ie", "phone": "+353861112222", "phone_display": "+353 86 111 2222", "whatsapp_number": "353861112222"}` →
    - no output file or `js/config.js` contains `bachintaxi@gmail.com`, `0330046` or `353870330046`
    - the `index.html` JSON-LD parses and has `"email": "new@x.ie"`
    - `config.js` contains `new@x.ie`
  - `test_config_js_cache_busted`: the `config.js?v=` value changes when the email changes.
- [ ] **Step 2:** Run. Expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run all tests. Expect PASS. Diff the default build's `index.html` against Task 3's output. Only marker removal and whitespace should differ.
- [ ] **Step 5:** Commit: `feat: editable page text and contact details`.

### Task 5: Photos in the generator

**Files:**
- Modify: `build/build.py`, `build/templates/index.html`
- Test: `tests/test_build_photos.py`

**Interfaces:**
- Consumes: `content["photo_slots"]`, `tour["photo"]`
- Produces: `content["_photos"]: dict[str, str]` maps photo id → relative path like `uploads/3fa9c2d1e0b4.jpg`. The publisher fills it (Task 8). The generator only reads it, and the referenced files must already exist in `out_dir/uploads/` before the build runs. Missing ids are treated as unset.
  - **Hero slot**: overrides the hero background with an inline `<style>` after the stylesheets, using the selector from `css/style.css:230`. It also overrides the `<link rel="preload">`, `og:image` and JSON-LD `image`.
  - **Taxi slot**: replaces `images/taxi.jpg` in the template `<img>`. Drop the fixed width and height, and use `object-fit` via an existing class.
  - **Logo slot**: `apple-touch-icon` and JSON-LD `logo`.
  - **Tour photo**: an `<img loading="lazy">` at the top of the card, and a photo in the tour detail page hero or above "About this tour". With no photo, the markup is identical to the current output.

- [ ] **Step 1: Write failing tests**
  - `test_hero_slot_used`: with slot hero set to `p1` and `_photos={"p1": "uploads/abc.jpg"}` (and the file created), `index.html` references `uploads/abc.jpg` in the style, preload and og:image.
  - `test_tour_photo_card_and_page`: the photo appears in the `ring-of-kerry` card on `index.html` and on its detail page with the correct relative root (`../uploads/…`).
  - `test_no_photo_unchanged`: the default build has no `uploads/` references.
  - `test_photo_filenames_are_content_hashed`: this one is really asserted by the publisher in Task 8. Here, assert that the generator uses `_photos` paths verbatim and never builds a filename from the slot name.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit: `feat: photo slots and tour photos in generator`.

### Task 6: Slug redirects and blog links

**Files:**
- Modify: `build/build.py`, `build/content.py`
- Test: `tests/test_redirects.py`

**Interfaces:**
- Produces in `build/content.py`:
  - `rename_slug(content_sections: dict, old: str, new: str) -> dict`: returns new `tours` and `redirects` sections.
    - Set `redirects[old] = new`.
    - Repoint every `k → old` redirect to `new`.
    - Drop `redirects[new]` if present, since a slug can be reused.
    - Never create a self-loop.
  - `blog_links_to(slug: str, redirects: dict) -> list[str]`: titles of `POSTS` whose body links `tours/<slug>.html`, or links a redirect source that resolves to `slug`.
- Generator: before rendering each post body, rewrite `tours/<src>.html` to `tours/<redirects[src]>.html`.

- [ ] **Step 1: Write failing tests**
  - `test_rename_rewrites_blog_links`: after renaming `ring-of-kerry` to `kerry-ring`, the build passes the link check and `blog/best-day-trips-from-dublin.html` links `../tours/kerry-ring.html`.
  - `test_rename_chain`: renaming a→b then b→c gives `redirects == {"a": "c", "b": "c"}`.
  - `test_rename_back_reuses_slug`: renaming a→b then b→a gives `redirects == {"b": "a"}`.
  - `test_blog_links_to`: `blog_links_to("cliffs-of-moher", {})` is non-empty, and `blog_links_to("meath-boyne-pub-trail", {})` is empty.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit: `feat: slug redirects and blog link rewriting`.

### Task 7: Postgres store

**Files:**
- Create: `server/__init__.py`, `server/store.py`
- Test: `tests/conftest.py`, `tests/test_store.py`

**Interfaces:**
- Produces in `server/store.py`:
  - `class Store(dsn: str)`, holding a `psycopg_pool.ConnectionPool` (add `psycopg-pool` to requirements) with `min_size=1, max_size=4`. Configure keepalives, because Railway's proxy drops idle connections.
  - `migrate() -> None`: idempotent. It creates:
    - `content(key text primary key, value jsonb not null, updated_at timestamptz not null default now())`
    - `photos(id text primary key, sha text not null unique, mime text not null, width int, height int, original_name text, data bytea not null, created_at timestamptz not null default now())`
  - `load() -> dict[str, Any]`: stored sections only.
  - `save_sections(changes: dict[str, Any]) -> None`: upserts all keys in one transaction. A value of `None` deletes that key.
  - `add_photo(data: bytes, mime: str, width: int, height: int, original_name: str) -> dict`: the id is `uuid4().hex[:12]` and the sha is sha256 hex. It returns the existing row's meta if the sha already exists.
  - `list_photos() -> list[dict]`: meta only, newest first. `get_photo(id) -> dict | None`, with data. `delete_photo(id) -> None`.
- `conftest.py`: a `store` fixture creates a unique schema per test in `TEST_DATABASE_URL` (via `options=-csearch_path=<schema>`), runs `migrate()`, and drops the schema afterwards. If `TEST_DATABASE_URL` is unset, the fixture **fails** with a clear message (it doesn't skip).

- [ ] **Step 1: Write failing tests**
  - `test_migrate_idempotent`
  - `test_save_and_load_sections`
  - `test_save_none_deletes`
  - `test_save_sections_atomic`: monkeypatch so the second upsert raises, then check that neither key was saved.
  - `test_add_photo_dedupes_by_sha`
  - `test_list_photos_excludes_data`
- [ ] **Step 2–4:** FAIL → implement → PASS (`TEST_DATABASE_URL=postgresql:///bch_taxi_test .venv/bin/pytest tests/test_store.py`).
- [ ] **Step 5:** Commit: `feat: postgres content and photo store`.

### Task 8: Publisher (build, commit, swap)

**Files:**
- Create: `server/publish.py`
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: `Store`, `build_site`, `BuildError`, `merge`, `default_content`, `ValidationError`
- Produces in `server/publish.py`:
  - `class Publisher(store: Store, site_root: Path)`
  - `rebuild() -> None`: builds from `store.load()` with no changes.
  - `apply(mutate: Callable[[dict], dict]) -> None`. Under a `threading.Lock`:
    1. `stored = store.load()`
    2. `view = merge(default_content(), stored)`
    3. `changes = mutate(view)`, a dict of section → new value, which may raise `ValidationError`
    4. `candidate = merge(default_content(), {**stored, **changes})`
    5. Write photos to `release/uploads/<sha[:12]>.<ext>` and set `candidate["_photos"]`.
    6. `build_site(candidate, release)`
    7. `store.save_sections(changes)`
    8. Swap the symlink.

    On any exception, delete the release dir, leave the DB and `current` untouched, and re-raise.
  - `current_dir() -> Path | None`
  - `content() -> dict`: the merged content currently live. It's cached and refreshed after each apply or rebuild.
- Releases live at `site_root/releases/<UTC yyyymmddHHMMSS>-<4 hex>`. Swap with `os.symlink(release, tmp)` then `os.replace(tmp, site_root/"current")`. Keep the newest 3 releases and delete the rest after the swap.

- [ ] **Step 1: Write failing tests** (with the `store` fixture and `tmp_path`)
  - `test_rebuild_creates_current`
  - `test_apply_success_saves_and_swaps`: change the email, then `current/js/config.js` contains the new email and `store.load()["settings"]["email"]` matches.
  - `test_apply_build_failure_keeps_old`: mutate so the build fails (monkeypatch `build_site` to raise `BuildError`), then `current` points to the same release as before, the DB is unchanged, and no extra release dir is left behind.
  - `test_apply_validation_error_keeps_old`
  - `test_apply_patches_only_changed_sections`: save `texts`, then call apply with a mutator that only returns `{"settings": …}` based on a view taken *before* the texts save. The texts survive.
  - `test_old_releases_pruned`: after 5 applies, there are ≤ 3 release dirs.
  - `test_photo_filenames_are_content_hashed`: two different photos assigned to the hero slot one after the other produce two different `uploads/` filenames in successive releases.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit: `feat: atomic publish with build-before-commit`.

### Task 9: Flask app and public site serving

**Files:**
- Create: `server/app.py`, `server/wsgi.py` (`app = create_app_from_env()`)
- Test: `tests/test_public.py`

**Interfaces:**
- Consumes: `Store`, `Publisher`
- Produces:
  - `create_app(store: Store, site_root: Path, *, admin_password: str, secret_key: str, testing: bool = False) -> Flask`
    - Runs `store.migrate()` and `Publisher.rebuild()` **synchronously before returning**.
    - Stores the publisher at `app.extensions["publisher"]`.
  - `create_app_from_env()` reads the env vars from Global Constraints. It refuses to start (raises) if `ADMIN_PASSWORD` is shorter than 12 characters or `SECRET_KEY` is missing.
- Public routes (everything that isn't `/admin…` or `/health`):
  - **Lookup order:** `path`, then `path.html`, then `path/index.html`, inside `current` only. Use `safe_join` or `send_from_directory`, so `..` traversal returns 404.
  - **Slug redirects:** `/tours/<old>` and `/tours/<old>.html` return 301 to `/tours/<new>.html` from `content()["redirects"]`.
  - **Unknown path:** serves `current/index.html` with status 404.
  - **Cache headers:** `Cache-Control: public, max-age=604800` for `/images/*` and `/uploads/*`, `public, max-age=3600` for `/css/*` and `/js/*`, `no-cache` for HTML. Use gzip if trivial (otherwise skip).
  - **`/health`:** 200 `ok` when `current_dir()` exists, else 503.
- Use `ProxyFix(x_for=1, x_proto=1)`.

- [ ] **Step 1: Write failing tests** (with the Flask test client)
  - `test_home_and_pretty_urls`: `/`, `/tours/ring-of-kerry`, `/tours/ring-of-kerry.html` and `/tours.html` all return 200.
  - `test_unknown_is_404_with_home`
  - `test_traversal_blocked`: `/../build/data.py`, `/%2e%2e/build/data.py` and `/build/data.py` all return 404, and the body has no `PHONE =`.
  - `test_cache_headers`
  - `test_slug_redirect`: store redirects `{"old": "ring-of-kerry"}`, then `/tours/old.html` returns 301 with Location `/tours/ring-of-kerry.html`.
  - `test_boot_builds_from_db_before_healthy`: save `{"settings": {"email": "boot@x.ie"}}` to the store, use a fresh empty `site_root`, then `create_app(...)`. `/health` is 200 and the first `/js/config.js` response contains `boot@x.ie`.
  - `test_env_guard`: `create_app_from_env` raises with a short password.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit: `feat: flask server for the generated site`.

### Task 10: Admin login, session, CSRF, rate limit

**Files:**
- Create: `server/admin/__init__.py` (blueprint `admin`, prefix `/admin`), `server/admin/auth.py`, `server/templates/admin/base.html`, `login.html`, `dashboard.html`, `server/static/admin.css`
- Test: `tests/test_admin_auth.py`

**Interfaces:**
- Produces:
  - `login_required` decorator.
  - `csrf_token()` Jinja global. Every admin POST must include a `csrf` form field that matches the session token, or it gets 400.
  - Shared `base.html` with nav links: Dashboard, Prices, Tours, Multi-day, Photos, Text, Contact, Log out.
  - `flash_ok(msg)` / `flash_err(msg)` helpers.
- Session settings:
  - `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE="Lax"`, `SESSION_COOKIE_SECURE = not testing`.
  - `PERMANENT_SESSION_LIFETIME=30 days`.
  - `MAX_CONTENT_LENGTH=25 MB`.
- Password check: `hmac.compare_digest(sha256(given), sha256(ADMIN_PASSWORD))`.
- Rate limit: an in-memory dict keyed by `request.remote_addr`. After 5 failed logins in 15 minutes, return 429 with "Too many attempts. Try again in 15 minutes." Clear it on success.
- Log out is a POST.
- Dashboard: links to each section, plus the email-confirmation banner when `flags.email_unconfirmed` is set (Task 11).

- [ ] **Step 1: Write failing tests**
  - `test_admin_redirects_to_login`
  - `test_login_wrong_password`
  - `test_login_ok_then_dashboard`
  - `test_post_without_csrf_400`
  - `test_rate_limit_after_5_failures`: the 6th try returns 429 even with the right password.
  - `test_logout_requires_post`
  - `test_cookie_flags`: in non-testing mode, the `Set-Cookie` has `Secure`, `HttpOnly` and `SameSite=Lax`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit: `feat: admin login with csrf and rate limit`.

### Task 11: Admin: prices, contact details, page text

**Files:**
- Create: `server/admin/prices.py`, `server/admin/settings.py`, `server/admin/texts.py`, and templates `prices.html`, `settings.html`, `texts.html`
- Test: `tests/test_admin_forms.py`

**Interfaces:**
- Consumes: `Publisher.apply`, `ValidationError`, `all_text_defaults()`
- **Prices** (`/admin/prices`):
  - One form. Each tour gets a row with its name, kind badge and a price input (blank = "Price on request").
  - Settings fields: multi-day rate, extra-hour rate, max passengers.
  - Airport fare rows (area, distance, to, from), each with a "remove" checkbox, plus 2 empty rows for adding.
  - Long transfer rows, in the same way.
  - On save, the mutator patches tour prices **by slug** on the fresh view. Unknown slugs are ignored, since a tour may have been deleted in another tab. It returns `tours`, `settings`, `airport_fares` and `long_transfers`.
  - Validation: rates must be ints from 0 to 100000, max passengers from 1 to 20, a fare row needs an area and both prices, and an empty row is ignored.
- **Contact** (`/admin/contact`): phone, phone display, email and WhatsApp number (digits only, with a hint: "country code, no + or spaces, e.g. 353870330046").
  - Validation: the email looks like an email, the phone matches `^\+?[0-9 ]{7,20}$`, and the WhatsApp number matches `^[0-9]{7,15}$`.
  - If the email changed, also set `flags.email_unconfirmed = <new email>`.
  - The dashboard and contact page then show a warning banner:

    > "Booking forms now send to <email>. **Bookings will not arrive until you confirm it:** send a test booking from the website, then click the activation link FormSubmit emails to <email>."

    The banner has an "I've confirmed it" button (POST) that clears the flag.
- **Text** (`/admin/text`):
  - Fields are grouped by group, and each group sits in a `<details>` section.
  - Each field shows its label, the default as a hint, and a textarea (multiline, or longer than 80 characters) or an input.
  - Each field has a "Reset to original" checkbox.
  - The mutator stores only values that differ from the default. Clearing a field to empty is rejected for required keys: every key is required except ones whose default is empty.
- After a successful save, redirect back with "Saved. The site is updated." After a build failure, re-render the form with the submitted values and the error "Couldn't publish: <details>. Nothing was changed."

- [ ] **Step 1: Write failing tests** (logged-in client)
  - `test_prices_update_live`: set `ring-of-kerry` to 499, then `/tours/ring-of-kerry.html` contains `€499`.
  - `test_price_blank_means_on_request`
  - `test_prices_ignore_deleted_slug`: a POST containing a slug that's no longer in the tours list is still saved OK.
  - `test_add_and_remove_airport_fare`
  - `test_prices_validation_rerenders_with_values`: a rate of "abc" returns 200, the error is shown, the submitted value is kept, and the DB is unchanged.
  - `test_email_change_sets_banner_and_config`
  - `test_confirm_clears_banner`
  - `test_text_override_and_reset`
  - `test_text_unchanged_not_stored`: submitting the text form untouched stores `texts == {}`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit: `feat: admin prices, contact and text editors`.

### Task 12: Admin: tours and multi-day routes

**Files:**
- Create: `server/admin/tours.py`, templates `tours_list.html`, `tour_edit.html`, `confirm_delete.html`, `multi_list.html`, `multi_edit.html`
- Test: `tests/test_admin_tours.py`

**Interfaces:**
- Consumes: `validate_tour`, `rename_slug`, `blog_links_to`, `KINDS`, `store.list_photos()`
- **Tours list** (`/admin/tours`):
  - Grouped by kind, with "Add day tour", "Add pub tour" and "Add golf trip" buttons (`/admin/tours/new?kind=pub`).
  - Each row shows the name, `price_label`, a Hidden badge, and a one-tap Hide/Show POST.
- **Edit** (`/admin/tours/<slug>`, and `/admin/tours/new`):
  - Fields: every tour field, plus kind, published, fav ("Most popular" badge) and photo.
  - The photo is chosen from a thumbnail radio grid with a "None" option.
  - Highlights are one per line.
  - Under the slug field: "This is the web address. Changing it keeps the old address working."
  - For a new tour, an empty slug is auto-generated from the name.
- **Delete** (`/admin/tours/<slug>/delete`): GET shows a confirmation page.
  - If `blog_links_to(slug)` is non-empty, it shows instead: "Can't delete: these blog posts link to this tour: … Hide it instead." with a Hide button.
  - The delete POST re-checks this server-side.
  - Deleting also removes redirects that point to the deleted slug.
- **Multi-day** (`/admin/multi-day`): list, edit, new and delete.
  - Fields: name, slug (unique, same regex), days (1–21), summary, plan (one line per day).
  - Validation: the number of plan lines must equal days ("You have 3 days but 2 day descriptions").
  - Slug changes for multi-day routes need no redirects, since they're only anchors.

- [ ] **Step 1: Write failing tests**
  - `test_new_golf_trip_appears`: create `golf`, `test-golf`, price 950, then `/golf-trips.html` contains it and `/tours/test-golf.html` contains `€950` and "per trip".
  - `test_edit_highlights_lines`
  - `test_hide_toggle`
  - `test_duplicate_slug_rejected`
  - `test_slug_change_redirects`: renaming `rock-of-cashel` to `cashel` makes `/tours/rock-of-cashel.html` return 301 to `/tours/cashel.html` and the blog link point to `cashel`.
  - `test_delete_blocked_when_blog_links`: deleting `cliffs-of-moher` is refused, and the tour remains.
  - `test_delete_unlinked_tour`: the starter pub tour can be deleted, and its page then returns 404.
  - `test_multi_day_plan_must_match_days`
  - `test_tour_photo_pick`: needs a photo in the store from a fixture JPEG, made with Pillow in the test.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit: `feat: admin tours and multi-day editors`.

### Task 13: Admin: photos

**Files:**
- Create: `server/images.py`, `server/admin/photos.py`, template `photos.html`
- Test: `tests/test_images.py`, `tests/test_admin_photos.py`

**Interfaces:**
- Produces in `server/images.py`:
  - `process_upload(raw: bytes) -> tuple[bytes, str, int, int]` returns `(data, mime, width, height)`:
    - Register `pillow_heif`'s opener once.
    - `Image.open`, then `ImageOps.exif_transpose`.
    - Shrink so the long edge is ≤ 2000 px.
    - If there's alpha, save as PNG (optimize). Otherwise convert to RGB and save as JPEG (quality 82, progressive).
    - Never pass `exif=`, so no metadata is kept.
    - Set `Image.MAX_IMAGE_PIXELS = 60_000_000`.
    - Raises `ImageError("That file isn't a photo we can use. Try a JPG or PNG.")` on `UnidentifiedImageError` or `DecompressionBombError`.
- `/admin/photos`:
  - The upload form uses `<input type="file" name="files" accept="image/*" multiple>`.
  - A thumbnail grid. Thumbnails come from `GET /admin/photos/<id>/raw`, which is login-required and reads from the DB.
  - Slot selects for Homepage hero, Taxi photo and Logo, with a "None (use original)" option.
  - Per photo: where it's used, plus a Delete button.
  - Delete is refused while the photo is in use: "Used by: Homepage hero, Ring of Kerry".
  - A 413 (too large) shows the friendly error "Photo too big (max 25 MB)".
- Upload doesn't publish anything by itself. Assigning a slot (or a tour photo, Task 12) goes through `Publisher.apply`.

- [ ] **Step 1: Write failing tests**
  - `test_upload_portrait_exif_rotated`: make a 400×200 JPEG with EXIF Orientation=6. After processing, width < height.
  - `test_upload_strips_gps`: the source has a GPSInfo EXIF entry, and `Image.open(out).getexif()` is empty.
  - `test_upload_heic`: write a small HEIC with `pillow_heif` in the test. It processes to `image/jpeg`.
  - `test_large_image_resized`: 5000×3000 → long edge 2000.
  - `test_png_alpha_kept_png`
  - `test_garbage_rejected`
  - `test_assign_hero_slot_live`: upload, assign the hero, then `/` references `uploads/<sha12>.jpg`, and that URL returns 200 with `max-age=604800`.
  - `test_delete_in_use_refused`
  - `test_raw_requires_login`
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Commit: `feat: admin photo uploads and slots`.

### Task 14: Phone-first admin styling and a manual check

**Files:**
- Modify: `server/static/admin.css`, admin templates

- [ ] **Step 1:** Style the admin:
  - One column at all widths below 900 px.
  - Inputs 16 px or larger, so iOS doesn't zoom.
  - Buttons ≥ 44 px tall.
  - On phones, a sticky bottom "Save" bar on long forms (prices, text, tour edit).
  - The nav collapses to a `<details>` menu.
  - Reuse the site palette (`#062a1f` and the gold from `css/style.css`).
- [ ] **Step 2:** Run locally:
  - `TEST_DATABASE_URL`-style DB `createdb bch_taxi_dev`
  - `DATABASE_URL=postgresql:///bch_taxi_dev ADMIN_PASSWORD=<12+ chars> SECRET_KEY=dev SITE_ROOT=/tmp/bch-dev .venv/bin/flask --app server.wsgi run -p 3400`

  Note that `SESSION_COOKIE_SECURE` needs `testing`/`FLASK_DEBUG=1` locally. Make `create_app_from_env` set it from `FLASK_DEBUG`.
- [ ] **Step 3:** With Playwright at 375×812 and at 1280×800:
  - log in
  - change a price, save, and see it on `/`
  - add a golf trip with a photo
  - edit the hero text
  - change the email and see the banner

  Take screenshots of each admin page, check there's no horizontal scroll (`document.documentElement.scrollWidth <= innerWidth`), and fix any issues.
- [ ] **Step 4:** Commit: `style: phone-first admin`.

### Task 15: Deploy files (stop before going live)

**Files:**
- Replace: `Dockerfile` with `FROM python:3.14-slim`:
  - `pip install --no-cache-dir -r requirements.txt`
  - COPY `build/`, `server/`, `css/`, `js/`, `images/`
  - `CMD gunicorn -w 1 --threads 8 -b 0.0.0.0:$PORT --timeout 60 server.wsgi:app`
- Delete: `Caddyfile`
- Modify: `railway.json`: set `healthcheckPath` to `/health` and `healthcheckTimeout` to 120. Update `.dockerignore` to exclude `.venv`, `dist`, `tests`, `docs`, `.env*` and `.git`.
- Create: `README.md`, covering how to run locally, how to run the tests, the env vars, the fact that content now lives in the DB and code defaults only apply until the owner overrides them, and how to change the admin password (the Railway variable `ADMIN_PASSWORD`).
- Modify: `build/data.py` docstring: "Defaults only. Live content is edited in /admin."

- [ ] **Step 1:** `docker` isn't installed locally, so check that the Dockerfile only references files that exist and that `gunicorn server.wsgi:app` starts locally (`.venv/bin/gunicorn -w 1 --threads 8 -b 127.0.0.1:3401 server.wsgi:app` with the dev env) and serves `/health` with 200.
- [ ] **Step 2:** Run the full suite: `TEST_DATABASE_URL=postgresql:///bch_taxi_test .venv/bin/pytest -q`. Expect all tests to pass.
- [ ] **Step 3:** Commit: `chore: python server deploy files`.
- [ ] **Step 4: STOP.** Report to the user and ask for an explicit go before any of the following:
  - adding Railway Postgres to project `bch-taxi`, since it's billable
  - setting `DATABASE_URL` (as a reference to the Postgres service), `ADMIN_PASSWORD` and `SECRET_KEY` on service `web` with `--skip-deploys`, without echoing them
  - `railway up -s web --detach | tail -n 4`

  After the go, verify `/health`, `/`, `/tours/ring-of-kerry`, `/golf-trips.html` and an admin login on the live URL.
