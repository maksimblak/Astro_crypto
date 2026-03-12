"""Migrate data from SQLite to DuckDB.

Usage: python scripts/migrate_to_duckdb.py
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

SQLITE_PATH = BASE_DIR / "data" / "btc_research.db"
DUCKDB_PATH = BASE_DIR / "data" / "btc_research.duckdb"


def migrate():
    import duckdb

    if not SQLITE_PATH.exists():
        print(f"SQLite database not found: {SQLITE_PATH}")
        sys.exit(1)

    if DUCKDB_PATH.exists():
        DUCKDB_PATH.unlink()
        print(f"Removed existing DuckDB: {DUCKDB_PATH}")

    conn = duckdb.connect(str(DUCKDB_PATH))
    conn.install_extension("sqlite")
    conn.load_extension("sqlite")

    # Attach SQLite as source
    conn.execute(f"ATTACH '{SQLITE_PATH}' AS sqlite_src (TYPE SQLITE)")

    # Get all tables from SQLite
    import sqlite3
    src = sqlite3.connect(str(SQLITE_PATH))
    tables = src.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"
    ).fetchall()
    src.close()

    for (table_name,) in tables:
        print(f"  Migrating {table_name}...", end=" ")
        conn.execute(
            f"CREATE TABLE {table_name} AS SELECT * FROM sqlite_src.{table_name}"
        )
        count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        print(f"{count} rows")

    conn.execute("DETACH sqlite_src")

    # Recreate indices
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pivots_type ON btc_pivots(type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pivots_date ON btc_pivots(date)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_market_features_version "
        "ON btc_market_features(feature_source_version)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_derivatives_history_source "
        "ON btc_derivatives_history(source)"
    )

    conn.close()
    size_mb = DUCKDB_PATH.stat().st_size / 1024 / 1024
    print(f"\nDone! DuckDB: {DUCKDB_PATH} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    migrate()
