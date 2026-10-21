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
