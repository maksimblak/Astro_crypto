"""Regime endpoint: /api/regime with Redis/memory cache."""

import duckdb
from fastapi import APIRouter, HTTPException

from backend.db import get_db, is_missing_relation
from backend.services import cache_service

router = APIRouter(tags=["regime"])

REGIME_CACHE_TTL = 300  # 5 minutes

_DESIRED_FEATURE_COLUMNS = [
    "amihud_illiquidity_20d", "amihud_z_90d", "range_compression_20d",
    "wiki_views", "wiki_views_7d", "wiki_views_z_30d",
    "fear_greed_value", "fear_greed_z_30d",
    "funding_rate_daily", "funding_rate_z_30d",
    "funding_price_divergence_3d", "funding_contrarian_bias_3d",
    "perp_premium_daily", "perp_premium_z_30d",
    "open_interest_value", "open_interest_delta_1d", "open_interest_delta_z_30d",
    "oi_price_state_1d", "open_interest_z_30d",
    "dxy_close", "dxy_return_20d", "dxy_return_z_90d",
    "us10y_yield", "us10y_change_20d_bps", "us10y_change_z_90d",
    "spx_close", "btc_spx_corr_30d",
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
    cached = cache_service.get("regime")
    if cached is not None:
        return cached

    from backend.services.regime_service import build_regime_payload

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
    cache_service.set("regime", result, ttl=REGIME_CACHE_TTL)
    return result
