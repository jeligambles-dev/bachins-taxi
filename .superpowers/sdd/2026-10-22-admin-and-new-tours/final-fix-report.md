# Final fix report

Command for every finding: `TEST_DATABASE_URL=postgresql:///bch_taxi_test .venv/bin/pytest -q`
Regression tests: `tests/test_final_fixes.py` (written first). RED run before any fix: `16 failed, 2 passed in 1.52s`
(the 2 passes were the "unchanged default" and "login CSRF still checked" guards). Final run: `216 passed`.

1. No airport fares -> 500. build.py min-fare falls back to "Fixed" when there are no fares; prices mutator rejects an empty fare list ("Keep at least one airport fare..."); forms.publish() also catches Exception, logs via log.exception, returns "Couldn't publish... Nothing was changed." Tests: test_no_airport_fares_builds, test_removing_every_fare_is_rejected, test_unexpected_exception_is_friendly. RED: ValueError min() of empty / RuntimeError escaping. GREEN: 4 passed.
2. Fare distance escaped with E(). Test: test_fare_distance_is_escaped. RED: raw `<b>` in output. GREEN.
3. Contact stale tab: hidden o__<field> inputs in settings.html; mutator keeps fresh value for unchanged fields. Test: test_contact_stale_tab_keeps_newer_phone. RED: phone_display reverted. GREEN.
4. Max passengers: build.py f-strings use MAX_PASSENGERS; group service name computed (N+1)+; config.js gets maxPax; main.js `MAX_PAX = Number(CFG.maxPax) || 8`. Built-in wording that states a bare 8 (TEXTS defaults, index template, modal partial, blog posts) goes through texts.dyn() which swaps in the limit; owner overrides are never touched, "8-seater"/"Up to 8 seats" stay. Admin still shows the original default. Tests: test_max_passengers_threaded, test_max_passengers_default_unchanged, test_main_js_reads_max_pax_from_config. RED: many leftover "Up to 8"/max="8". GREEN.
5. Upload: MAX_CONTENT_LENGTH 100 MB; per-file 25 MB cap skipped with reason in handler (reads at most cap+1 bytes); 413 text "Too much at once (max 100 MB per upload). Try fewer photos at a time." Tests: test_request_limit_100mb, test_oversize_single_file_skipped_with_reason, test_413_message_reworded (+ updated test_too_big_is_friendly and the config assertion in test_admin_auth). GREEN.
6. Footer: favs, then FOOTER_FALLBACK (glendalough, connemara, dingle) skipping missing/hidden, then other day tours, max 6. Test: test_default_footer_matches_original (passes alongside existing test_footer_survives_missing_hardcoded_slugs). RED: order/list differed.
7. Session fingerprint: hmac(SECRET_KEY, password) hexdigest[:32]. Test: test_session_fingerprint_not_plain_hash. GREEN.
8. Cache busting: asset() appends ?v=<sha8 of file> to style.css, pages.css, main.js, calculator.js in subpages and index. Test: test_assets_versioned. GREEN.
9. Modal prices use toLocaleString('en-IE') via euro(). Test: test_modal_price_has_thousands_separator (source check, no JS runtime in suite). GREEN.
10. check_csrf redirects anonymous non-login POSTs to /admin/login before touching request.form; login POST still CSRF-checked. Tests: test_unauth_post_rejected_before_form_parse, test_login_post_still_csrf_checked. RED: form parsed. GREEN.
11. Leftover-token BuildError lists unique tokens only ("Unknown placeholder {{FOO}} in page text", max 3 + "and N more"). Test: test_leftover_token_error_is_concise. RED: 28 entries. GREEN.

Final output: `216 passed in ~23s`.
