# BCH Taxi: "Dark executive" redesign

Date: 2026-11-08 · Status: draft for owner review · Base branch: `design/modern` (what is live now)

## Why

The current site works and its content is right, but the owner wants it **cleaner, more modern and suitable for a fleet**. It should be clearly better than other Irish taxi and chauffeur sites. We looked at Lynk, Cosgrove's / Executive Chauffeurs Ireland, Redmond, iDrive and Ireland VIP Tours. Their common weaknesses:

- They show no prices up front.
- The fleet is a paragraph of model names, with no seats, bags or photos for each vehicle.
- The photos are old.
- Calls to action are repeated and the pages are cluttered.

BCH already has the strongest feature of the lot: instant fixed prices in the booking card. The redesign has to make that and the fleet look premium, with less clutter.

The owner chose direction **B · Dark executive** from three mockups. The mockup is saved next to this file as `2026-11-08-dark-executive-redesign-mockup.png` (the middle one of the three).

## Goals

1. Apply the B look to **every public page**: home, Fleet, Business, Partners, Help, Tours hub, Pub tours, Golf trips, Multi-day tours, each tour page, Destinations, Price calculator, Blog index and posts.
2. Make the fleet feel like a real operator's fleet. Each vehicle class gets a spec sheet: passengers, suitcases, "from" price or "Quote", access features, and a photo.
3. Make every page **cleaner**. Use fewer bordered cards, more space and one clear primary action per section.
4. Make it look as good on phones as on desktop. Most bookings are assumed to come from phones (owner agreed to this assumption).

## Non-goals

- **No content changes.** The vehicle classes, tours, prices, texts, business/partner offers and contact details stay as they are.
- The four fleet classes stay as they are: executive saloon, premium MPV, 8-seater van and minibus/coach. The owner chose to keep them now.
- **No changes to `/admin`.** It keeps its look, and everything the owner can edit there must keep working and keep showing up on the site.
- No change to how booking, pricing, address search, FormSubmit enquiries or the publish/rebuild flow work.
- No new pages and no new backend features.

## Anti-goals (a failure even if it "works")

- Any owner-edited value from `/admin` no longer shows, or shows in the wrong place.
- The booking card loses a feature: instant price, address search, tabs, vehicle choice or tour selection.
- It looks like a template, or the yellow takes over. Yellow is for primary buttons and small accents only.
- Text is hard to read: low contrast on black, or text smaller than the current 17px minimum for reading text.
- Pages get slower or heavier in a way you can notice.

## Look and feel (decided by the owner via mockup B)

- **Colours:** true near-black background (about `#0B0B0C`) instead of the current dark green. Use near-white text and soft grey secondary text. Raised surfaces are slightly lighter blacks, separated by hairlines rather than shadows. Taxi yellow (about `#FFC72C`) is used only for primary buttons, the active tab underline and small accents like the eyebrow label.
- **Type:** headlines in a serif display face (the mockup used *Instrument Serif*). Body and UI text stay in *Geist*. Small uppercase letter-spaced labels are used for eyebrows and form field labels.
- **Hero:** a full-bleed photo with a soft dark gradient, the nav over the photo, a small yellow eyebrow and a large serif headline. The booking bar floats over the bottom of the photo as a dark frosted-glass bar.
- **Fleet showcase (home and Fleet page):** one vehicle is featured large, with the photo on the left and on the right its name, a one-line description, a 2×2 spec grid and a yellow "Book this vehicle" button. The other classes sit underneath as tabs with a thin top rule. The active tab has a yellow rule, and clicking a tab swaps the featured vehicle. The 8-seater van is featured by default.
- **Sections:** generous vertical space, a serif section title on the left and a short grey intro on the right on desktop. Fewer boxed cards. Where cards stay (tours, for example), they are flat with hairline borders and photo-led.

## Pages

Every page gets the new colours, type, nav, footer and spacing. Specific notes:

- **Home:** B hero with the booking bar. After that come services (airport, intercity, events), tours with prices, the fleet showcase, then business and partners. The "Trips shaped around you" tile row is merged or slimmed so the page is less boxy. The exact order and merging are left to the builder, as long as all the content stays reachable.
- **Fleet:** every class shown as a full spec sheet, featured-style, stacked down the page, not small cards.
- **Tours hub, listings and tour pages:** flat, photo-led tour cards with the price clearly shown. Tour pages use the new hero, and the booking card keeps its current behaviour.
- **Business, Partners, Help, Destinations, Calculator, Blog:** new hero, new section style and the existing content. Forms keep their fields and behaviour and are restyled to fit the dark theme with readable inputs.

## Constraints

- The site is generated by `build/build.py`. It writes static pages to `dist/` from `build/templates/index.html`, with `css/style.css` and `css/pages.css`. The `/admin` panel rebuilds pages on save. The work is mainly in the CSS and the HTML that `build.py` emits.
- The existing tests (`TEST_DATABASE_URL=postgresql:///bch_taxi_test .venv/bin/pytest -q`) must still pass. Where a test checks old markup that has to change, update the test so it still checks what that test was there to protect.
- Fonts are loaded from Google Fonts, as Geist is today.
- Phones: no horizontal scroll, comfortable tap targets, and the booking bar becomes a stacked card on narrow screens.
- Accessibility: keep visible focus rings, alt text and the current contrast standard.
- Deploy stays `railway up -s web --detach`. Nothing goes live until the owner has seen it running locally and says go.

## Hero copy (owner approved the mockup wording)

- The new default homepage headline is "Arrive the way you planned." and it stays editable in `/admin` (`home.hero_title`). If the owner has already set a headline there, theirs still wins.
- A small yellow eyebrow label above it reads "Private transport · Ireland". It is added as a new editable text key with that default. This is the only new copy.
- Other pages keep their existing headlines in the new style.

## Decisions made after the builder check (Claude's calls, owner to confirm)

- **Booking bar = a new skin on the existing booking card, not a new form.** On desktop it shows the same tabs (Taxi & airport / Tours) above a horizontal row of the same fields, with the same instant price and "See price" step. On phones it becomes a stacked card. All current behaviour in `main.js`, `places.js` and `fares.js` stays, and tour pages get the same treatment.
- **Spec grid values come only from existing fleet data, so admin edits flow through:**
  - Passengers and Suitcases come from `passengers` and `bags`.
  - Price shows "Tours from €X" only for the vehicle the fixed tour and airport prices apply to, where X is the lowest published tour price. Every other vehicle shows its `price_note` text.
  - The fourth cell shows the first feature, or "Wheelchair access" when a feature mentions it.
  - No new admin fields.
- **Any number of vehicles.** The tab row and the Fleet page handle whatever the admin has published (add and delete exist there). The featured default is the vehicle with slug `van` if published, otherwise the first published vehicle.
- **"Book this vehicle"** jumps to the booking card with that vehicle pre-selected in its existing vehicle field. On the Fleet page it links to the homepage booking card with the vehicle pre-selected. If that vehicle has no instant price, the existing "price confirmed when you enquire" path runs.

## Left to the builder

- Exact colour, spacing and type-scale values within the direction above.
- Whether the fleet tab switching uses a small amount of JS or a no-JS fallback that shows all four.
- How to slim the home page's tile rows and which sections merge.
- Restyling details for tables, FAQ accordions and the blog.

## Open items carried over (not part of this work)

- The owner should review the 4 starter pub and golf trips, whose copy was written by Claude and whose prices are unset.
- Send one real test booking to confirm FormSubmit still delivers.
- `design/modern` is not merged to `main` or pushed to GitHub.
