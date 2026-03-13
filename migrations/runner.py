"""Simple DuckDB migration runner.

Tracks applied migrations in a `_migrations` table.
Migration files are Python scripts in migrations/versions/ with
an `upgrade(conn)` and `downgrade(conn)` function.

Usage:
    python -m migrations.runner upgrade     # apply all pending
    python -m migrations.runner downgrade   # rollback last one
    python -m migrations.runner status      # show applied vs pending
"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = str(BASE_DIR / "data" / "btc_research.duckdb")
VERSIONS_DIR = Path(__file__).resolve().parent / "versions"


def _connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(DB_PATH)


def _ensure_migrations_table(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            version VARCHAR PRIMARY KEY,
            applied_at VARCHAR NOT NULL,
            description VARCHAR DEFAULT ''
        )
    """)


def _get_applied(conn: duckdb.DuckDBPyConnection) -> set[str]:
    rows = conn.execute("SELECT version FROM _migrations ORDER BY version").fetchall()
    return {row[0] for row in rows}


def _get_available() -> list[tuple[str, Path]]:
    """Return sorted list of (version_name, path) from versions/ dir."""
    if not VERSIONS_DIR.exists():
        return []
    files = sorted(VERSIONS_DIR.glob("*.py"))
    return [(f.stem, f) for f in files if f.stem != "__init__"]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(f"migrations.versions.{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade() -> list[str]:
    """Apply all pending migrations. Returns list of applied versions."""
    conn = _connect()
    _ensure_migrations_table(conn)
    applied = _get_applied(conn)
    available = _get_available()
    newly_applied = []

    for version, path in available:
        if version in applied:
            continue
        module = _load_module(version, path)
        print(f"  Applying {version}...")
        try:
            module.upgrade(conn)
            conn.execute(
                "INSERT INTO _migrations (version, applied_at, description) VALUES (?, ?, ?)",
                [version, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 getattr(module, "description", "")],
            )
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"  FAILED {version}")
            raise
        newly_applied.append(version)
        print(f"  Applied {version}")

    conn.close()
    return newly_applied


def downgrade(steps: int = 1) -> list[str]:
    """Rollback last N migrations. Returns list of rolled back versions."""
    conn = _connect()
    _ensure_migrations_table(conn)
    applied = sorted(_get_applied(conn), reverse=True)
    available = dict(_get_available())
    rolled_back = []

    for version in applied[:steps]:
        if version not in available:
            print(f"  WARNING: {version} applied but file not found, skipping")
            continue
        module = _load_module(version, available[version])
        print(f"  Rolling back {version}...")
        try:
            module.downgrade(conn)
            conn.execute("DELETE FROM _migrations WHERE version = ?", [version])
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"  FAILED rolling back {version}")
            raise
        rolled_back.append(version)
        print(f"  Rolled back {version}")

    conn.close()
    return rolled_back


def status() -> None:
    """Print migration status."""
    conn = _connect()
    _ensure_migrations_table(conn)
    applied = _get_applied(conn)
    available = _get_available()
    conn.close()

    print(f"\nMigrations in {VERSIONS_DIR}:")
    print(f"{'Version':<40} {'Status':<12}")
    print("-" * 52)
    for version, _ in available:
        state = "applied" if version in applied else "PENDING"
        print(f"{version:<40} {state:<12}")

    orphans = applied - {v for v, _ in available}
    if orphans:
        print(f"\nOrphaned (applied but file missing): {', '.join(sorted(orphans))}")
    print()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "upgrade":
        result = upgrade()
        print(f"\nApplied {len(result)} migration(s).")
    elif cmd == "downgrade":
        steps = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        result = downgrade(steps)
        print(f"\nRolled back {len(result)} migration(s).")
    elif cmd == "status":
        status()
    else:
        print(f"Unknown command: {cmd}. Use: upgrade | downgrade | status")
