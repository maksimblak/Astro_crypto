"""
BTC Astro Dashboard — Flask backend.
Запуск: python dashboard.py
Открыть: http://localhost:5000
"""

import sqlite3
import os
from datetime import date
import numpy as np
from flask import Flask, Response, jsonify, render_template

try:
    from .market_regime import build_regime_payload
except ImportError:
    from market_regime import build_regime_payload

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "btc_research.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def derive_thresholds(reference_scores):
    scores = np.asarray(reference_scores, dtype=float)
    if len(scores) == 0:
        return [0.5, 1.0, 1.5, 2.0]

    raw = sorted({round(float(np.quantile(scores, q)), 1) for q in [0.75, 0.85, 0.90, 0.95]})
    thresholds = [value for value in raw if value > 0]
    if not thresholds:
        return [0.5, 1.0, 1.5, 2.0]
    while len(thresholds) < 4:
        thresholds.append(round(thresholds[-1] + 0.5, 1))
    return thresholds[:4]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/favicon.ico")
def favicon():
    return Response(status=204)


@app.route("/api/calendar")
def api_calendar():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, score, direction, moon_sign, moon_element, quarter, "
            "eclipse_days, moon_ingress, tension, harmony, retro_planets, "
            "station_planets, details FROM btc_astro_calendar ORDER BY date"
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return jsonify({"error": "Table btc_astro_calendar not found. Run astro_scoring.py first."}), 404
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/pivots")
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
        return jsonify({"error": "Table btc_pivot_astro_v2 not found. Run astro_extended_analysis.py first."}), 404
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/daily")
def api_daily():
    conn = get_db()
    rows = conn.execute("SELECT date, close FROM btc_daily ORDER BY date").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/regime")
def api_regime():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM btc_daily ORDER BY date"
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return jsonify({"error": "Table btc_daily not found. Run research/main.py first."}), 404

    conn.close()
    if not rows:
        return jsonify({"error": "No market data found in btc_daily."}), 404
    return jsonify(build_regime_payload(rows))


@app.route("/api/today")
def api_today():
    conn = get_db()
    try:
        fields = (
            "SELECT date, score, direction, moon_sign, moon_element, quarter, "
            "eclipse_days, moon_ingress, tension, harmony, retro_planets, "
            "station_planets, details FROM btc_astro_calendar "
        )
        target_date = date.today().isoformat()
        row = conn.execute(fields + "WHERE date = ?", (target_date,)).fetchone()
        if row is None:
            row = conn.execute(fields + "WHERE date >= ? ORDER BY date LIMIT 1", (target_date,)).fetchone()
        if row is None:
            row = conn.execute(fields + "ORDER BY date DESC LIMIT 1").fetchone()
    except sqlite3.OperationalError:
        conn.close()
        return jsonify({"error": "Calendar not generated yet."}), 404
    conn.close()
    if row:
        return jsonify(dict(row))
    return jsonify({})


@app.route("/api/stats")
def api_stats():
    """Out-of-sample model statistics from historical holdout data."""
    conn = get_db()
    try:
        period = conn.execute(
            "SELECT MIN(date) as start_date, MAX(date) as end_date, COUNT(*) as total_days "
            "FROM btc_astro_history WHERE sample_split = 'test'"
        ).fetchone()
    except sqlite3.OperationalError:
        conn.close()
        return jsonify({"error": "Table btc_astro_history not found. Run astro_scoring.py first."}), 404

    base_scores = [
        row["score"]
        for row in conn.execute(
            "SELECT score FROM btc_astro_history "
            "WHERE sample_split = 'test' AND is_pivot = 0"
        ).fetchall()
    ]
    score_thresholds = derive_thresholds(base_scores)

    baseline = conn.execute(
        "SELECT AVG(score) as avg_score FROM btc_astro_history "
        "WHERE sample_split = 'test' AND is_pivot = 0"
    ).fetchone()
    baseline_avg = round(baseline["avg_score"], 2) if baseline["avg_score"] else 0

    pivot_avg_row = conn.execute(
        "SELECT AVG(h.score) as avg_score, COUNT(*) as cnt "
        "FROM btc_pivots p "
        "JOIN btc_astro_history h ON h.date = p.date "
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
        "SUM(CASE WHEN (h.direction > 0 AND p.type LIKE '%high') OR (h.direction < 0 AND p.type LIKE '%low') THEN 1 ELSE 0 END) as correct "
        "FROM btc_pivots p "
        "JOIN btc_astro_history h ON h.date = p.date "
        "WHERE h.sample_split = 'test' AND h.direction != 0"
    ).fetchone()
    dir_total = dir_stats["total"] if dir_stats["total"] else 0
    dir_correct = dir_stats["correct"] if dir_stats["correct"] else 0
    dir_accuracy = round(dir_correct / dir_total * 100, 1) if dir_total > 0 else 0

    conn.close()

    return jsonify({
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
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
