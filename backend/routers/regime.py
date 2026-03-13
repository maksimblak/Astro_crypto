"""Regime endpoint: /api/regime with TTL cache."""

import threading

from cachetools import TTLCache
import duckdb
from fastapi import APIRouter, HTTPException

from backend.db import get_db, is_missing_relation

router = APIRouter(tags=["regime"])

_regime_cache: TTLCache = TTLCache(maxsize=1, ttl=300)
_regime_lock = threading.Lock()

_DESIRED_FEATURE_COLUMNS = [
    "amihud_illiquidity_20d", "amihud_z_90d", "range_compression_20d",
    "wiki_views", "wiki_views_7d", "wiki_views_z_30d",
    "fear_greed_value", "fear_greed_z_30d",
    "funding_rate_daily", "funding_rate_z_30d",
    "perp_premium_daily", "perp_premium_z_30d",
    "open_interest_value", "open_interest_z_30d",
    "unique_addresses", "unique_addresses_z_30d",
    "tx_count", "tx_count_z_30d", "onchain_activity_z_30d",
]


def _market_feature_select_sql(conn) -> str:
    try:
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(btc_market_features)").fetchall()
        }
    except duckdb.Error:
        return ""

    parts = []
    for col in _DESIRED_FEATURE_COLUMNS:
        parts.append(f"f.{col}" if col in existing else f"NULL AS {col}")
    return ", " + ", ".join(parts) if parts else ""


@router.get("/regime")
def api_regime():
    with _regime_lock:
        cached = _regime_cache.get("regime")
        if cached is not None:
            return cached

    from market_regime import build_regime_payload

    try:
        with get_db() as conn:
            feature_select = _market_feature_select_sql(conn)
            rows = conn.execute(
                "SELECT d.date, d.open, d.high, d.low, d.close, d.volume"
                + feature_select
                + " FROM btc_daily d"
                " LEFT JOIN btc_market_features f ON f.date = d.date"
                " ORDER BY d.date"
            ).fetchall()
    except duckdb.Error as exc:
        if is_missing_relation(exc, "btc_daily"):
            raise HTTPException(404, "Table btc_daily not found. Run research/main.py first.") from exc
        try:
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT date, open, high, low, close, volume FROM btc_daily ORDER BY date"
                ).fetchall()
        except duckdb.Error as fallback_exc:
            if is_missing_relation(fallback_exc, "btc_daily"):
                raise HTTPException(404, "Table btc_daily not found. Run research/main.py first.") from fallback_exc
            raise HTTPException(500, "Failed to query market regime inputs.") from fallback_exc

    if not rows:
        raise HTTPException(404, "No market data found in btc_daily.")

    result = build_regime_payload(rows)
    with _regime_lock:
        _regime_cache["regime"] = result
    return result
