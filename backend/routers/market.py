"""Market endpoints: /api/daily, /api/pivots."""

import sqlite3

from fastapi import APIRouter, HTTPException

from backend.db import get_db

router = APIRouter(tags=["market"])


@router.get("/daily")
def api_daily():
    conn = get_db()
    rows = conn.execute("SELECT date, close FROM btc_daily ORDER BY date").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/pivots")
def api_pivots():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, price, pivot_type, pct_change, is_high, is_major, "
            "moon_quarter, moon_sign, moon_element, retro_count, tension_count, "
            "harmony_count, eclipse_days, near_eclipse FROM btc_pivot_astro_v2 ORDER BY date"
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        raise HTTPException(404, "Table btc_pivot_astro_v2 not found. Run astro_extended_analysis.py first.")
    conn.close()
    return [dict(r) for r in rows]
