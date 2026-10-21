"""Postgres store: owner content overrides (one jsonb row per section) and photos."""
import hashlib
import uuid
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

_SCHEMA = """
create table if not exists content (
    key text primary key,
    value jsonb not null,
    updated_at timestamptz not null default now()
);
create table if not exists photos (
    id text primary key,
    sha text not null unique,
    mime text not null,
    width int,
    height int,
    original_name text,
    data bytea not null,
    created_at timestamptz not null default now()
);
"""

_META = "id, sha, mime, width, height, original_name, created_at"


def _meta(row: dict) -> dict:
    row = dict(row)
    row["created_at"] = row["created_at"].isoformat()
    return row


class Store:
    """Pooled Postgres store.

    `schema` (optional) pins every connection's search_path to that schema;
    tests use it for per-test isolation. Production leaves it None.
    """

    def __init__(self, dsn: str, schema: str | None = None):
        kwargs: dict[str, Any] = {
            "row_factory": dict_row,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        }
        if schema:
            kwargs["options"] = f"-csearch_path={schema}"
        self.pool = ConnectionPool(
            dsn,
            min_size=1,
            max_size=4,
            kwargs=kwargs,
            check=ConnectionPool.check_connection,
            open=False,
        )
        self.pool.open(wait=True)

    def close(self) -> None:
        self.pool.close()

    def migrate(self) -> None:
        with self.pool.connection() as conn:
            conn.execute(_SCHEMA)

    def load(self) -> dict[str, Any]:
        with self.pool.connection() as conn:
            rows = conn.execute("select key, value from content").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def _upsert(self, cur, key: str, value: Any) -> None:
        if value is None:
            cur.execute("delete from content where key = %s", (key,))
        else:
            cur.execute(
                "insert into content (key, value) values (%s, %s) "
                "on conflict (key) do update "
                "set value = excluded.value, updated_at = now()",
                (key, Jsonb(value)),
            )

    def save_sections(self, changes: dict[str, Any]) -> None:
        with self.pool.connection() as conn:  # one transaction; rolls back on error
            with conn.cursor() as cur:
                for key, value in changes.items():
                    self._upsert(cur, key, value)

    def add_photo(self, data: bytes, mime: str, width: int, height: int,
                  original_name: str) -> dict:
        sha = hashlib.sha256(data).hexdigest()
        with self.pool.connection() as conn:
            row = conn.execute(
                f"insert into photos (id, sha, mime, width, height, original_name, data) "
                f"values (%s, %s, %s, %s, %s, %s, %s) "
                f"on conflict (sha) do nothing returning {_META}",
                (uuid.uuid4().hex[:12], sha, mime, width, height, original_name, data),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    f"select {_META} from photos where sha = %s", (sha,)
                ).fetchone()
        return _meta(row)

    def list_photos(self) -> list[dict]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"select {_META} from photos order by created_at desc, id"
            ).fetchall()
        return [_meta(r) for r in rows]

    def get_photo(self, photo_id: str) -> dict | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                f"select {_META}, data from photos where id = %s", (photo_id,)
            ).fetchone()
        if row is None:
            return None
        row["data"] = bytes(row["data"])
        return _meta(row)

    def delete_photo(self, photo_id: str) -> None:
        with self.pool.connection() as conn:
            conn.execute("delete from photos where id = %s", (photo_id,))
