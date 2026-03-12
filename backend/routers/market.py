"""Market endpoints: /api/daily, /api/pivots."""

from fastapi import APIRouter, HTTPException

from backend.db import get_db

router = APIRouter(tags=["market"])


@router.get("/daily")
def api_daily():
    with get_db() as conn:
        try:
            rows = conn.execute("SELECT date, close FROM btc_daily ORDER BY date").fetchall()
        except Exception:
            raise HTTPException(404, "Table btc_daily not found. Run research/main.py first.")
    return rows


@router.get("/pivots")
def api_pivots():
    with get_db() as conn:
        try:
            rows = conn.execute(
                "SELECT date, price, pivot_type, pct_change, is_high, is_major, "
                "moon_quarter, moon_sign, moon_element, retro_count, tension_count, "
                "harmony_count, eclipse_days, near_eclipse FROM btc_pivot_astro_v2 ORDER BY date"
            ).fetchall()
        except Exception:
            raise HTTPException(404, "Table btc_pivot_astro_v2 not found. Run astro_extended_analysis.py first.")
    return rows
