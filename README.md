# BCH Taxi website

A Flask server that builds the public site from the database and serves it, plus an owner admin at `/admin`. Hosted on Railway (Dockerfile, one gunicorn worker).

## How it works

- Content (tours, prices, texts, photos, settings) lives in Postgres. The code defaults in `build/data.py` and `build/texts.py` apply only until the owner overrides them in the admin.
- On boot the server runs migrations and builds the whole site from the DB into `SITE_ROOT`. `/health` returns 503 until that build succeeds. Every admin save rebuilds and swaps the live release.
- The container disk is not persistent, so the site is rebuilt from the DB on every start.
- Blog posts are code-edited (`build/posts.py`), not in the admin.

## Run locally

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
createdb bch_taxi_dev
export DATABASE_URL=postgresql:///bch_taxi_dev
export ADMIN_PASSWORD='choose-at-least-12-characters'
export SECRET_KEY=dev
export SITE_ROOT=/tmp/bch-site
.venv/bin/flask --app server.wsgi:app run --port 3401
```

Or with gunicorn, as in production: `.venv/bin/gunicorn -w 1 --threads 8 -b 127.0.0.1:3401 server.wsgi:app`.

Open http://127.0.0.1:3401/ and http://127.0.0.1:3401/admin.

To build a static copy without the server: `python3 build/build.py` (writes to `dist/`).

## Tests

```sh
createdb bch_taxi_test
TEST_DATABASE_URL=postgresql:///bch_taxi_test .venv/bin/pytest -q
```

`TEST_DATABASE_URL` is required (tests fail without it). Each test uses a throwaway schema.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Postgres connection string (on Railway, a reference to the Postgres service) |
| `ADMIN_PASSWORD` | Owner login password, 12+ characters |
| `SECRET_KEY` | Signs session cookies; use a long random value |
| `SITE_ROOT` | Where releases are built (default `/tmp/bch-site`) |
| `PORT` | Set by Railway |

## Admin

- URL: `/admin`. One login, no history or undo.
- Change the password: set the Railway variable `ADMIN_PASSWORD` on service `web` and redeploy. This also logs out every existing session.
- Booking emails: the booking forms post to `https://formsubmit.co/ajax/<email from admin>`. The first time an email is set (or changed), FormSubmit sends a confirmation email to that address. Click the link in it once, or bookings will not be delivered. Send a test booking after changing the address.

## Editing defaults in code

- `build/data.py`: default tours, prices, rates, contact details.
- `build/texts.py`: default page copy.
- `build/posts.py`: blog posts (always edited here).

Code defaults only show for anything the owner has not overridden in the admin.
