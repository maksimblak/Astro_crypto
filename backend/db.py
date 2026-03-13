"""Database connection helper (DuckDB)."""

import os
import time
from contextlib import contextmanager

import duckdb

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "btc_research.duckdb")

_READ_RETRIES = 3
_READ_RETRY_DELAY = 1.0  # seconds


class _DictCursor:
    """Wraps a DuckDB connection to return dict-like rows (compatible with sqlite3.Row)."""

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self._conn = conn

    def execute(self, sql: str, params=None):
        if params is not None:
            self._result = self._conn.execute(sql, params)
        else:
            self._result = self._conn.execute(sql)
        return self

    def fetchone(self):
        row = self._result.fetchone()
        if row is None:
            return None
        cols = [desc[0] for desc in self._result.description]
        return dict(zip(cols, row))

    def fetchall(self):
        cols = [desc[0] for desc in self._result.description]
        return [dict(zip(cols, row)) for row in self._result.fetchall()]


@contextmanager
def get_db():
    """Open a read-only DuckDB connection with retries for write-lock conflicts."""
    last_exc = None
    for attempt in range(_READ_RETRIES):
        try:
            conn = duckdb.connect(DB_PATH, read_only=True)
            break
        except duckdb.IOException as exc:
            last_exc = exc
            if attempt < _READ_RETRIES - 1:
                time.sleep(_READ_RETRY_DELAY)
    else:
        raise last_exc  # type: ignore[misc]
    try:
        yield _DictCursor(conn)
    finally:
        conn.close()


@contextmanager
def get_db_write():
    conn = duckdb.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def is_missing_relation(exc: Exception, *relation_names: str) -> bool:
    """Best-effort check for missing DuckDB tables/views in query failures."""
    message = str(exc).lower()
    if "does not exist" not in message:
        return False
    return any(name.lower() in message for name in relation_names)
