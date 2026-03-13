"""Astro endpoints: /api/today, /api/calendar, /api/stats."""

from datetime import date

import duckdb
import numpy as np
from fastapi import APIRouter, HTTPException

from backend.db import get_db, is_missing_relation

router = APIRouter(tags=["astro"])


def _derive_thresholds(reference_scores, pivot_scores=None):
    base = np.asarray(reference_scores, dtype=float)
    if len(base) == 0:
        return [0.5, 1.0, 1.5, 2.0]

    if pivot_scores is not None:
        pivots = np.asarray(pivot_scores, dtype=float)
        if len(pivots) > 0:
            all_scores = np.concatenate([base, pivots])
            unique = sorted(t for t in set(round(float(s), 1) for s in all_scores) if t > 0)
            thresholds = []
            for target_pct in (3.0, 5.0, 8.0, 12.0):
                for t in unique:
                    p_above = int((pivots >= t).sum())
                    b_above = int((base >= t).sum())
                    if p_above + b_above == 0:
                        continue
                    if p_above / (p_above + b_above) * 100 >= target_pct:
                        thresholds.append(t)
                        break
            thresholds = sorted(set(thresholds))
            if thresholds:
                while len(thresholds) < 4:
                    thresholds.append(round(thresholds[-1] + 0.5, 1))
                return thresholds[:4]

    raw = sorted({round(float(np.quantile(base, q)), 1) for q in [0.75, 0.85, 0.90, 0.95]})
    thresholds = [value for value in raw if value > 0]
    if not thresholds:
        return [0.5, 1.0, 1.5, 2.0]
    while len(thresholds) < 4:
        thresholds.append(round(thresholds[-1] + 0.5, 1))
    return thresholds[:4]


_CALENDAR_FIELDS = (
    "date, score, direction, moon_sign, moon_element, quarter, "
    "eclipse_days, moon_ingress, tension, harmony, retro_planets, "
    "station_planets, sun_sign, sun_element, details"
)


@router.get("/today")
def api_today():
    try:
        with get_db() as conn:
            target_date = date.today().isoformat()
            row = conn.execute(
                f"SELECT {_CALENDAR_FIELDS} FROM btc_astro_calendar WHERE date = ?",
                (target_date,),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    f"SELECT {_CALENDAR_FIELDS} FROM btc_astro_calendar WHERE date >= ? ORDER BY date LIMIT 1",
                    (target_date,),
                ).fetchone()
            if row is None:
                row = conn.execute(
                    f"SELECT {_CALENDAR_FIELDS} FROM btc_astro_calendar ORDER BY date DESC LIMIT 1"
                ).fetchone()
    except duckdb.Error as exc:
        if is_missing_relation(exc, "btc_astro_calendar"):
            raise HTTPException(404, "Calendar not generated yet.") from exc
        raise HTTPException(500, "Failed to query astro calendar.") from exc
    return row if row else {}


@router.get("/calendar")
def api_calendar():
    try:
        with get_db() as conn:
            rows = conn.execute(
                f"SELECT {_CALENDAR_FIELDS} FROM btc_astro_calendar ORDER BY date"
            ).fetchall()
    except duckdb.Error as exc:
        if is_missing_relation(exc, "btc_astro_calendar"):
            raise HTTPException(404, "Table btc_astro_calendar not found. Run astro_scoring.py first.") from exc
        raise HTTPException(500, "Failed to query astro calendar history.") from exc
    return rows


@router.get("/stats")
def api_stats():
    try:
        with get_db() as conn:
            period = conn.execute(
                "SELECT MIN(date) as start_date, MAX(date) as end_date, COUNT(*) as total_days "
                "FROM btc_astro_history WHERE sample_split = 'test'"
            ).fetchone()

            base_scores = [
                row["score"]
                for row in conn.execute(
                    "SELECT score FROM btc_astro_history WHERE sample_split = 'test' AND is_pivot = 0"
                ).fetchall()
            ]
            pivot_scores = [
                row["score"]
                for row in conn.execute(
                    "SELECT h.score FROM btc_pivots p "
                    "JOIN btc_astro_history h ON h.date = p.date "
                    "WHERE h.sample_split = 'test'"
                ).fetchall()
            ]
            score_thresholds = _derive_thresholds(base_scores, pivot_scores)

            baseline = conn.execute(
                "SELECT AVG(score) as avg_score FROM btc_astro_history "
                "WHERE sample_split = 'test' AND is_pivot = 0"
            ).fetchone()
            baseline_avg = round(baseline["avg_score"], 2) if baseline["avg_score"] else 0

            pivot_avg_row = conn.execute(
                "SELECT AVG(h.score) as avg_score, COUNT(*) as cnt "
                "FROM btc_pivots p JOIN btc_astro_history h ON h.date = p.date "
                "WHERE h.sample_split = 'test'"
            ).fetchone()
            pivot_avg = round(pivot_avg_row["avg_score"], 2) if pivot_avg_row["avg_score"] else 0
            total_pivots = pivot_avg_row["cnt"]
            total_days = period["total_days"] if period["total_days"] else 0

            thresholds = []
            for threshold in score_thresholds:
                days_above = conn.execute(
                    "SELECT COUNT(*) as c FROM btc_astro_history "
                    "WHERE sample_split = 'test' AND score >= ?",
                    (threshold,),
                ).fetchone()["c"]
                pivots_above = conn.execute(
                    "SELECT COUNT(*) as c FROM btc_pivots p "
                    "JOIN btc_astro_history h ON h.date = p.date "
                    "WHERE h.sample_split = 'test' AND h.score >= ?",
                    (threshold,),
                ).fetchone()["c"]

                days_pct = round(days_above / total_days * 100, 1) if total_days else 0
                expected_rate = days_above / total_days if total_days else 0
                actual_rate = pivots_above / total_pivots if total_pivots else 0
                lift = round(actual_rate / expected_rate, 2) if expected_rate > 0 else 0

                thresholds.append({
                    "threshold": threshold,
                    "days_count": days_above,
                    "days_pct": days_pct,
                    "pivots_in_zone": pivots_above,
                    "lift": lift,
                })

            dir_stats = conn.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN (h.direction > 0 AND p.type LIKE '%high') "
                "OR (h.direction < 0 AND p.type LIKE '%low') THEN 1 ELSE 0 END) as correct "
                "FROM btc_pivots p JOIN btc_astro_history h ON h.date = p.date "
                "WHERE h.sample_split = 'test' AND h.direction != 0"
            ).fetchone()
            dir_total = dir_stats["total"] if dir_stats["total"] else 0
            dir_correct = dir_stats["correct"] if dir_stats["correct"] else 0
            dir_accuracy = round(dir_correct / dir_total * 100, 1) if dir_total > 0 else 0
    except duckdb.Error as exc:
        if is_missing_relation(exc, "btc_astro_history"):
            raise HTTPException(404, "Table btc_astro_history not found. Run astro_scoring.py first.") from exc
        if is_missing_relation(exc, "btc_pivots"):
            raise HTTPException(404, "Table btc_pivots not found. Run research/main.py first.") from exc
        raise HTTPException(500, "Failed to compute astro statistics.") from exc

    return {
        "baseline_avg_score": baseline_avg,
        "pivot_avg_score": pivot_avg,
        "pivot_matched": total_pivots,
        "total_calendar_days": total_days,
        "total_pivots": total_pivots,
        "thresholds": thresholds,
        "score_scale": {
            "cool": score_thresholds[0],
            "warm": score_thresholds[1],
            "hot": score_thresholds[2],
            "extreme": score_thresholds[3],
        },
        "direction_accuracy": dir_accuracy,
        "direction_total": dir_total,
        "direction_correct": dir_correct,
        "period_start": period["start_date"],
        "period_end": period["end_date"],
        "period_label": "holdout",
    }
