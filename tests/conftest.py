import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "build"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


import uuid

import pytest


@pytest.fixture
def store():
    """A Store on a throwaway schema (t_<uuid>) inside TEST_DATABASE_URL.

    Uses Store(dsn, schema=...), which sets search_path per connection.
    Fails (does not skip) when TEST_DATABASE_URL is unset.
    """
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.fail(
            "TEST_DATABASE_URL is not set. Run: createdb bch_taxi_test && "
            "export TEST_DATABASE_URL=postgresql:///bch_taxi_test"
        )
    import psycopg
    from server.store import Store

    schema = "t_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(f'CREATE SCHEMA "{schema}"')
    s = Store(dsn, schema=schema)
    try:
        s.migrate()
        yield s
    finally:
        s.close()
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(f'DROP SCHEMA "{schema}" CASCADE')


ADMIN_PASSWORD = "correct-horse-battery"


@pytest.fixture
def app(store, tmp_path):
    from server.app import create_app

    return create_app(store, tmp_path / "site", admin_password=ADMIN_PASSWORD,
                      secret_key="k", testing=True)


@pytest.fixture
def client(app):
    return app.test_client()


def csrf_of(client):
    """The CSRF token in this client's session (GETs the login page if none)."""
    with client.session_transaction() as s:
        tok = s.get("csrf")
    if tok is None:
        client.get("/admin/login")
        with client.session_transaction() as s:
            tok = s["csrf"]
    return tok


@pytest.fixture
def logged_in(client):
    """A test client with a valid admin session. Use csrf_of(logged_in) for
    the token to put in POST forms."""
    r = client.post("/admin/login", data={"password": ADMIN_PASSWORD,
                                          "csrf": csrf_of(client)})
    assert r.status_code == 302
    return client
