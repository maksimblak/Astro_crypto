"""
BTC Astro Dashboard — Flask backend.
Запуск: python dashboard.py
Открыть: http://localhost:5000
"""

import sqlite3
import os
from flask import Flask, jsonify, render_template

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "btc_research.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/calendar")
def api_calendar():
    conn = get_db()
    rows = conn.execute(
        "SELECT date, score, direction, moon_sign, moon_element, quarter, "
        "eclipse_days, moon_ingress, tension, harmony, retro_planets, "
        "station_planets, details FROM btc_astro_calendar ORDER BY date"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/pivots")
def api_pivots():
    conn = get_db()
    rows = conn.execute(
        "SELECT date, price, pivot_type, pct_change, is_high, is_major, "
        "moon_quarter, moon_sign, moon_element, retro_count, tension_count, "
        "harmony_count, eclipse_days FROM btc_pivot_astro_v2 ORDER BY date"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/daily")
def api_daily():
    conn = get_db()
    rows = conn.execute(
        "SELECT date, close FROM btc_daily WHERE date >= '2020-01-01' ORDER BY date"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/today")
def api_today():
    conn = get_db()
    row = conn.execute(
        "SELECT date, score, direction, moon_sign, moon_element, quarter, "
        "eclipse_days, moon_ingress, tension, harmony, retro_planets, "
        "station_planets, details FROM btc_astro_calendar "
        "ORDER BY ABS(julianday(date) - julianday('now')) LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        return jsonify(dict(row))
    return jsonify({})


@app.route("/api/stats")
def api_stats():
    """Model statistics: average scores, thresholds, direction accuracy."""
    conn = get_db()

    # Baseline: average score across all calendar days
    baseline = conn.execute(
        "SELECT AVG(score) as avg_score FROM btc_astro_calendar"
    ).fetchone()
    baseline_avg = round(baseline["avg_score"], 2) if baseline["avg_score"] else 0

    # Average score of actual pivot days (matched to calendar)
    pivot_avg_row = conn.execute(
        "SELECT AVG(c.score) as avg_score, COUNT(*) as cnt "
        "FROM btc_pivot_astro_v2 p "
        "JOIN btc_astro_calendar c ON c.date = p.date"
    ).fetchone()
    pivot_avg = round(pivot_avg_row["avg_score"], 2) if pivot_avg_row["avg_score"] else 0
    pivot_matched = pivot_avg_row["cnt"]

    # Threshold analysis
    total_cal = conn.execute("SELECT COUNT(*) as c FROM btc_astro_calendar").fetchone()["c"]
    total_pivots = conn.execute("SELECT COUNT(*) as c FROM btc_pivot_astro_v2").fetchone()["c"]

    thresholds = []
    for t in [2, 3, 5, 7]:
        cal_above = conn.execute(
            "SELECT COUNT(*) as c FROM btc_astro_calendar WHERE score >= ?", (t,)
        ).fetchone()["c"]

        # Pivots that happened on days with score >= threshold
        # Using btc_pivots (171 rows) matched against calendar
        pivots_above = conn.execute(
            "SELECT COUNT(*) as c FROM btc_pivots p "
            "JOIN btc_astro_calendar c ON c.date = p.date WHERE c.score >= ?", (t,)
        ).fetchone()["c"]

        # Also check pivots from btc_pivot_astro_v2 with retro_count + tension_count as proxy score
        pivot_v2_above = conn.execute(
            "SELECT COUNT(*) as c FROM btc_pivot_astro_v2 "
            "WHERE (retro_count + tension_count + eclipse_days) >= ?", (t,)
        ).fetchone()["c"]

        pct_days = round(cal_above / total_cal * 100, 1) if total_cal else 0
        # Lift = (pivots in high-score days / total pivots) / (high-score days / total days)
        expected_rate = cal_above / total_cal if total_cal else 1
        actual_rate = pivots_above / total_pivots if total_pivots else 0
        lift = round(actual_rate / expected_rate, 2) if expected_rate > 0 else 0

        thresholds.append({
            "threshold": t,
            "days_count": cal_above,
            "days_pct": pct_days,
            "pivots_in_zone": pivots_above,
            "lift": lift,
        })

    # Direction accuracy from btc_pivot_astro_v2
    # direction in calendar: positive = top, negative = bottom
    dir_stats = conn.execute(
        "SELECT COUNT(*) as total, "
        "SUM(CASE WHEN (c.direction > 0 AND p.is_high = 1) OR (c.direction < 0 AND p.is_high = 0) THEN 1 ELSE 0 END) as correct "
        "FROM btc_pivot_astro_v2 p "
        "JOIN btc_astro_calendar c ON c.date = p.date "
        "WHERE c.direction != 0"
    ).fetchone()
    dir_total = dir_stats["total"] if dir_stats["total"] else 0
    dir_correct = dir_stats["correct"] if dir_stats["correct"] else 0
    dir_accuracy = round(dir_correct / dir_total * 100, 1) if dir_total > 0 else 0

    conn.close()

    return jsonify({
        "baseline_avg_score": baseline_avg,
        "pivot_avg_score": pivot_avg,
        "pivot_matched": pivot_matched,
        "total_calendar_days": total_cal,
        "total_pivots": total_pivots,
        "thresholds": thresholds,
        "direction_accuracy": dir_accuracy,
        "direction_total": dir_total,
        "direction_correct": dir_correct,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
