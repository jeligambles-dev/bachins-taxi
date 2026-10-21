# BCH Taxi: owner admin + Rural Pub Tours + Golf Trips

Date: 2026-10-22 · Status: draft for review

## Why

Today every price, tour and line of text on the BCH Taxi site lives in code
(`build/data.py`, `build/posts.py`, and hand-written HTML in `index.html`).
Changing anything means editing Python, running `python3 build/build.py` and
redeploying to Railway. The owner of the taxi business wants to change things
themselves, whenever they want, without a developer.

At the same time the site gets two new kinds of trip: **Rural Pub Tours** and
**Golf Trips**.

Success = the owner opens the admin on their phone, changes a price or swaps
a photo, saves, and sees it on the live site seconds later.

## Who

- **One admin: the owner.** Uses both phone and computer, so every admin
  screen must be comfortable on a phone (big tap targets, one column, no wide
  tables, photo upload from the camera roll).
- Visitors: unchanged experience, same fast static pages.

## Goals

1. **Admin section** at `/admin`, password-protected, where the owner can edit:
   - **Prices:** every tour price, airport fares (to/from per area), long
     transfers (Galway, Cork, …), `MULTI_DAY_RATE`, `EXTRA_HOUR_RATE`,
     `MAX_PASSENGERS`, and multi-day routes (days, summary, day plan).
   - **Tours:** add, edit, hide (unpublish without deleting) and delete tours.
     Every field a tour has today is editable: name, slug, region, area,
     price, favourite flag, duration, drive time, short description,
     highlights, intro.
   - **Photos:** upload images and assign them. At minimum: the homepage hero,
     the logo/taxi images already in `images/`, and an optional main photo
     per tour (tours have no photos today; the tour card and tour page should
     show the photo when one is set and look as they do now when not).
   - **Page text:** headings, intros and body copy across the site, including
     the homepage text that is currently hand-written in `index.html` outside
     the `<!-- @… -->` regions, and contact details (`PHONE`,
     `PHONE_DISPLAY`, `EMAIL`, `WHATSAPP`).
2. **Changes go live in seconds** on save, with no code edit and no redeploy.
3. **Rural Pub Tours** and **Golf Trips** added as new trip types alongside
   the existing tours (the user approved "next to the existing tours"). Each
   gets its own section/listing and individual pages like the current tours,
   with "From €X" pricing.
   - Seed them with a few sensible starter entries and rewritten copy, but
     **prices are placeholders** for the owner to fill in via admin. Don't
     invent real prices. Until a price is set, the site should show something
     honest such as "Price on request" rather than "€0" or "€X".
   - Pub tours: country pubs, trad music, driver gets everyone home safely.
     Golf trips: driver to well-known Irish courses, single or multi-day,
     room for clubs.

## Non-goals (agreed)

- Editing blog posts (`build/posts.py` stays code-edited).
- More than one admin login / user accounts.
- Change history / undo.

## Anti-goals

- The owner losing edits on redeploy or restart. Content must live in
  durable storage, not in the container filesystem.
- Visitors seeing a slower or broken site. A failed rebuild must leave the
  last good pages online.
- An admin that's painful on a phone.
- An admin anyone can get into. The login must resist guessing (rate-limit
  attempts), use a secure, HttpOnly session cookie, and the password lives in
  a Railway env var, never in the repo.

## Current state (for the builder)

- Repo: `/Volumes/Jeli's NVMe/Projects/bachins-taxi`, GitHub
  `jeligambles-dev/bachins-taxi`. **Much of the current site is uncommitted**
  (`build/`, `css/`, `blog/`, Dockerfile, Caddyfile, etc.); commit the
  existing state first, as its own commit, before starting.
- Generator: `build/build.py` reads `build/data.py` and writes `tours/*.html`,
  `tours.html`, `multi-day-tours.html`, `price-calculator.html`,
  `destinations.html`, `blog/`, `sitemap.xml`, and fills marked regions of
  `index.html`. It exits non-zero on broken local links.
- Deploy: Railway project `bch-taxi`, service `web`, Caddy static image
  (Dockerfile + Caddyfile), URL https://web-production-95242.up.railway.app.

## How it gets made (my calls, user did not object)

- Stay on Railway. Add a small server process to the `web` service plus a
  **Railway Postgres** database holding prices, tours, page text and photos
  (photos as DB rows or a Railway volume, builder's choice, as long as
  they're durable).
- **Keep the existing Python generator** as the renderer. On save, the server
  loads content from the DB, runs the generator into a fresh directory and
  swaps it in atomically only if the build succeeds; otherwise keep the old
  pages and show the owner the error.
- On first boot, seed the DB from the current `data.py` and `index.html`
  text so nothing changes visually on day one.
- Visitors keep getting static files (Caddy, or the new server serving the
  built directory, builder's choice). Keep pretty URLs, caching headers and
  404 behaviour from the Caddyfile.
- Target extra cost: a few dollars a month (one small Postgres).

## Decisions from review (marked [my call] where I decided, not the user)

- **Database is the only source of content after the first seed** [my call].
  `data.py` becomes a one-time seed: the seed runs only when the DB is empty,
  so redeploys never overwrite the owner's edits.
- **"Page text" means all visible copy** [my call], including copy that's
  hard-coded in `build/build.py`: CTA bands, group band, calculator and
  destinations intros, homepage FAQ, and the homepage JSON-LD contact details.
- **Hide, delete and rename tours** [my call]:
  - *Hide* removes the tour from listings, but its page stays reachable, so
    blog links keep working.
  - *Delete* is blocked when a blog post links to the tour; admin says which
    post links to it and suggests hiding instead.
  - *Changing a slug* keeps a redirect from the old URL.
- **Pub tours and golf trips placement** [my call]: they get their own
  listing pages and detail pages, appear in the homepage tours grid, the nav
  and the booking-form "Service" dropdown, and reuse the tour fields.
- **Golf trips have one fixed "From €X" price per trip** (user), even when
  they last several days. They aren't priced per day and have no day plan.
  The duration field can say e.g. "3 days".
- **Booking forms follow the email set in admin** (user). Today `js/main.js`
  posts to `https://formsubmit.co/ajax/bachintaxi@gmail.com`, and the
  WhatsApp link there is hard-coded too. Both must come from the admin
  settings. FormSubmit only delivers to a new address after its activation
  link is clicked. When the email is changed, admin must show a clear
  warning saying that bookings won't arrive until the confirmation email
  sent to the new address is clicked, and it should explain how to trigger
  that email (for example by sending a test booking).

## Left to the builder

- Server language/framework (Python fits since the generator is Python).
- Admin UI look and structure, as long as it's phone-first and simple.
- How page text is broken into editable fields.
- Image resizing/compression on upload (recommended: keep pages fast).
- Exact slugs, nav labels and starter entries for pub tours and golf trips.
