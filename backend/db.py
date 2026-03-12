"""Database connection helper (DuckDB)."""

import os
from contextlib import contextmanager

import duckdb

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "btc_research.duckdb")


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
    conn = duckdb.connect(DB_PATH, read_only=True)
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
    finally:
        conn.close()
