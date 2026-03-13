"""Threshold configuration service backed by DuckDB.

Stores regime/model thresholds in `btc_config` table.
Falls back to hardcoded defaults if table or key is missing.
Enables A/B testing by changing thresholds without code deploys.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from backend.db import get_db, get_db_write

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default thresholds — used when table is empty or key missing
# ---------------------------------------------------------------------------

DEFAULTS: dict[str, dict[str, Any]] = {
    # --- Direction thresholds ---
    "direction": {
        "close_vs_200_strong": 0.10,
        "sma50_vs_200_strong": 0.05,
        "momentum_20_strong": 0.08,
        "momentum_20_mild": 0.03,
        "momentum_90_very_strong": 0.25,
        "momentum_90_strong": 0.10,
        "drawdown_shallow": -0.10,
        "drawdown_moderate": -0.20,
        "drawdown_deep": -0.35,
        "drawdown_extreme": -0.50,
        "volume_spike_z": 1.5,
    },
    # --- Stress thresholds ---
    "stress": {
        "amihud_z_high": 1.5,
        "amihud_z_elevated": 0.75,
        "range_expansion_high": 1.75,
        "range_expansion_elevated": 1.35,
        "volume_shock_z": 2.0,
    },
    # --- Context thresholds ---
    "context": {
        "wiki_z_high": 1.30,
        "wiki_z_low": -1.20,
        "fear_greed_greedy": 70,
        "fear_greed_fearful": 24,
        "funding_z_high": 0.98,
        "funding_z_low": -1.12,
        "funding_divergence_mild": 0.60,
        "funding_divergence_strong": 1.20,
        "perp_premium_high": 0.00019,
        "perp_premium_low": -0.00026,
        "oi_z_low": -1.48,
        "oi_z_high": 0.42,
        "oi_delta_z_elevated": 0.75,
        "addresses_z_high": 0.91,
        "addresses_z_low": -0.90,
        "dxy_return_elevated": 0.03,
        "dxy_return_high": 0.05,
        "us10y_change_elevated_bps": 25.0,
        "us10y_change_high_bps": 50.0,
        "btc_spx_corr_high": 0.55,
        "btc_spx_corr_low": 0.20,
    },
    # --- Regime classification thresholds ---
    "regime": {
        "strong_bull": 10,
        "mild_bull": 4,
        "strong_bear": -11,
        "mild_bear": -6,
        "distribution": -2,
        "recovery_drawdown": -0.18,
    },
    # --- Model thresholds ---
    "model": {
        "fdr_threshold": 0.25,
        "min_binary_weight": 0.15,
        "min_continuous_weight": 0.05,
        "min_direction_weight": 0.10,
        "weight_shrinkage_factor": 0.85,
    },
}


def ensure_config_table() -> None:
    """Create btc_config table if it doesn't exist."""
    try:
        with get_db_write() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS btc_config (
                    category VARCHAR NOT NULL,
                    key VARCHAR NOT NULL,
                    value DOUBLE NOT NULL,
                    description VARCHAR DEFAULT '',
                    updated_at VARCHAR NOT NULL,
                    PRIMARY KEY (category, key)
                )
            """)
    except Exception:
        logger.exception("Failed to create btc_config table")


def seed_defaults(overwrite: bool = False) -> int:
    """Populate btc_config with default values. Returns count of inserted rows."""
    ensure_config_table()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inserted = 0

    try:
        with get_db_write() as conn:
            for category, keys in DEFAULTS.items():
                for key, value in keys.items():
                    if overwrite:
                        conn.execute(
                            "DELETE FROM btc_config WHERE category = ? AND key = ?",
                            [category, key],
                        )
                    existing = conn.execute(
                        "SELECT 1 FROM btc_config WHERE category = ? AND key = ?",
                        [category, key],
                    ).fetchone()
                    if existing is None:
                        conn.execute(
                            "INSERT INTO btc_config (category, key, value, updated_at) "
                            "VALUES (?, ?, ?, ?)",
                            [category, key, float(value), now],
                        )
                        inserted += 1
    except Exception:
        logger.exception("Failed to seed btc_config defaults")

    return inserted


def get_thresholds(category: str) -> dict[str, float]:
    """Load thresholds for a category. Falls back to DEFAULTS on error."""
    defaults = DEFAULTS.get(category, {})
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT key, value FROM btc_config WHERE category = ?",
                (category,),
            ).fetchall()
            if rows:
                loaded = {row["key"]: row["value"] for row in rows}
                return {**{k: float(v) for k, v in defaults.items()}, **loaded}
    except Exception:
        logger.debug("btc_config read failed for %s, using defaults", category)
    return {k: float(v) for k, v in defaults.items()}


def set_threshold(category: str, key: str, value: float) -> None:
    """Update a single threshold value."""
    ensure_config_table()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with get_db_write() as conn:
            existing = conn.execute(
                "SELECT 1 FROM btc_config WHERE category = ? AND key = ?",
                [category, key],
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE btc_config SET value = ?, updated_at = ? "
                    "WHERE category = ? AND key = ?",
                    [float(value), now, category, key],
                )
            else:
                conn.execute(
                    "INSERT INTO btc_config (category, key, value, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    [category, key, float(value), now],
                )
    except Exception:
        logger.exception("Failed to set threshold %s.%s", category, key)


def get_all_config() -> dict[str, dict[str, float]]:
    """Return all config grouped by category."""
    result: dict[str, dict[str, float]] = {}
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT category, key, value FROM btc_config ORDER BY category, key"
            ).fetchall()
            for row in rows:
                cat = row["category"]
                if cat not in result:
                    result[cat] = {}
                result[cat][row["key"]] = row["value"]
    except Exception:
        logger.debug("btc_config read all failed, returning defaults")
        return {cat: {k: float(v) for k, v in keys.items()} for cat, keys in DEFAULTS.items()}
    return result
