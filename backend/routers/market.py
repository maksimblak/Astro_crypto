"""Market endpoints: /api/daily, /api/pivots."""

import duckdb
from fastapi import APIRouter, HTTPException

from backend.db import get_db, is_missing_relation

router = APIRouter(tags=["market"])


@router.get("/daily")
def api_daily():
    try:
        with get_db() as conn:
            rows = conn.execute("SELECT date, close FROM btc_daily ORDER BY date").fetchall()
    except duckdb.Error as exc:
        if is_missing_relation(exc, "btc_daily"):
            raise HTTPException(404, "Table btc_daily not found. Run research/main.py first.") from exc
        raise HTTPException(500, "Failed to query btc_daily.") from exc
    return rows


@router.get("/pivots")
def api_pivots():
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT date, price, pivot_type, pct_change, is_high, is_major, "
                "moon_quarter, moon_sign, moon_element, retro_count, tension_count, "
                "harmony_count, eclipse_days, near_eclipse FROM btc_pivot_astro_v2 ORDER BY date"
            ).fetchall()
    except duckdb.Error as exc:
        if is_missing_relation(exc, "btc_pivot_astro_v2"):
            raise HTTPException(404, "Table btc_pivot_astro_v2 not found. Run astro_extended_analysis.py first.") from exc
        raise HTTPException(500, "Failed to query pivot data.") from exc
    return rows
