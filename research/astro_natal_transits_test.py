"""
BTC x natal astrology: проверка теории натальной карты BTC.

Скрипт фиксирует "дату рождения" BTC, строит натальные позиции и проверяет,
чаще ли медленные транзиты к этим натальным точкам совпадают с историческими
разворотами BTC, чем с обычными днями.
"""

from __future__ import annotations

import argparse
import math
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

import ephem
import numpy as np
import pandas as pd
from scipy import stats

try:
    from .astro_shared import DB_PATH, apply_bh_correction
except ImportError:
    from astro_shared import DB_PATH, apply_bh_correction


DEFAULT_BIRTH_SPECS = [
    "whitepaper_date_utc_midnight=2008-10-31T00:00:00",
    "genesis_block=2009-01-03T18:15:05",
    "network_launch_date_utc_midnight=2009-01-09T00:00:00",
]

TRANSIT_BODIES = {
    "Марс": ephem.Mars,
    "Юпитер": ephem.Jupiter,
    "Сатурн": ephem.Saturn,
}

NATAL_BODIES = {
    "Солнце": ephem.Sun,
    "Луна": ephem.Moon,
    "Меркурий": ephem.Mercury,
    "Венера": ephem.Venus,
    "Марс": ephem.Mars,
    "Юпитер": ephem.Jupiter,
    "Сатурн": ephem.Saturn,
}

ASPECTS = {
    "соединение": 0.0,
    "квадрат": 90.0,
    "трин": 120.0,
    "оппозиция": 180.0,
}


@dataclass
class CandidateResult:
    name: str
    birth_dt: datetime
    pivot_count: int
    baseline_count: int
    pivot_hit_mean: float
    baseline_hit_mean: float
    mw_p_value: float
    key_feature_rows: list[dict]


def angular_distance_deg(a_deg: float, b_deg: float) -> float:
    diff = abs((a_deg - b_deg) % 360.0)
    return min(diff, 360.0 - diff)


def longitude_deg(body_cls, when: datetime) -> float:
    body = body_cls(ephem.Date(when))
    return float(ephem.Ecliptic(body).lon) * 180.0 / math.pi


def parse_birth_specs(specs: list[str]) -> list[tuple[str, datetime]]:
    parsed = []
    for spec in specs:
        if "=" in spec:
            name, value = spec.split("=", 1)
        else:
            name, value = "custom", spec
        parsed.append((name.strip(), datetime.fromisoformat(value.strip())))
    return parsed


def load_market_data(start: str | None, end: str | None) -> tuple[pd.DataFrame, set[pd.Timestamp]]:
    conn = sqlite3.connect(DB_PATH)

    daily_query = "SELECT date, close FROM btc_daily"
    pivots_query = "SELECT date FROM btc_pivots"
    params = []
    filters = []

    if start:
        filters.append("date >= ?")
        params.append(start)
    if end:
        filters.append("date <= ?")
        params.append(end)

    if filters:
        where = " WHERE " + " AND ".join(filters)
        daily_query += where
        pivots_query += where

    daily_query += " ORDER BY date"
    pivots_query += " ORDER BY date"

    daily_df = pd.read_sql(daily_query, conn, params=params)
    pivots_df = pd.read_sql(pivots_query, conn, params=params)
    conn.close()

    daily_df["date"] = pd.to_datetime(daily_df["date"])
    pivots_df["date"] = pd.to_datetime(pivots_df["date"])
    pivot_dates = set(pivots_df["date"])
    return daily_df, pivot_dates


def build_transit_cache(daily_df: pd.DataFrame) -> dict[pd.Timestamp, dict[str, float]]:
    cache = {}
    for idx, row in daily_df.iterrows():
        when = row["date"].to_pydatetime()
        cache[row["date"]] = {name: longitude_deg(body_cls, when) for name, body_cls in TRANSIT_BODIES.items()}
        if (idx + 1) % 500 == 0:
            print(f"  transit cache: {idx + 1}/{len(daily_df)}")
    return cache


def build_natal_positions(birth_dt: datetime) -> dict[str, float]:
    return {name: longitude_deg(body_cls, birth_dt) for name, body_cls in NATAL_BODIES.items()}


def build_feature_frame(
    daily_df: pd.DataFrame,
    pivot_dates: set[pd.Timestamp],
    transit_cache: dict[pd.Timestamp, dict[str, float]],
    natal_positions: dict[str, float],
    orb_deg: float,
) -> pd.DataFrame:
    rows = []
    for idx, row in daily_df.iterrows():
        date = row["date"]
        transit_positions = transit_cache[date]
        features = []

        for transit_name, transit_lon in transit_positions.items():
            for natal_name, natal_lon in natal_positions.items():
                distance = angular_distance_deg(transit_lon, natal_lon)
                for aspect_name, target_angle in ASPECTS.items():
                    orb = abs(distance - target_angle)
                    if orb <= orb_deg:
                        features.append(f"{transit_name}→нат.{natal_name} {aspect_name}")

        saturn_saturn_orb = min(
            abs(angular_distance_deg(transit_positions["Сатурн"], natal_positions["Сатурн"]) - angle)
            for angle in ASPECTS.values()
        )

        rows.append(
            {
                "date": date,
                "close": row["close"],
                "is_pivot": date in pivot_dates,
                "natal_hit_count": len(features),
                "saturn_to_natal_saturn_orb": round(saturn_saturn_orb, 3),
                "features": features,
            }
        )

        if (idx + 1) % 750 == 0:
            print(f"  natal features: {idx + 1}/{len(daily_df)}")

    return pd.DataFrame(rows)


def evaluate_features(feature_df: pd.DataFrame, min_support: int, top_n: int) -> list[dict]:
    pivots = feature_df[feature_df["is_pivot"]]
    baseline = feature_df[~feature_df["is_pivot"]]

    pivot_counts = Counter()
    baseline_counts = Counter()
    for features in pivots["features"]:
        pivot_counts.update(features)
    for features in baseline["features"]:
        baseline_counts.update(features)

    rows = []
    for feature_name, pivot_hits in pivot_counts.items():
        if pivot_hits < min_support:
            continue
        baseline_rate = baseline_counts[feature_name] / max(len(baseline), 1)
        pivot_rate = pivot_hits / max(len(pivots), 1)
        if baseline_rate <= 0:
            continue  # признак отсутствует в baseline — тест бессмыслен
        p_value = stats.binomtest(pivot_hits, len(pivots), baseline_rate).pvalue
        lift = pivot_rate / baseline_rate
        rows.append(
            {
                "feature": feature_name,
                "pivot_hits": pivot_hits,
                "pivot_pct": round(pivot_rate * 100, 1),
                "baseline_pct": round(baseline_rate * 100, 1),
                "lift": round(lift, 2) if np.isfinite(lift) else None,
                "p_value": round(float(p_value), 4),
            }
        )

    apply_bh_correction(rows, p_key="p_value", q_key="q_value")
    rows.sort(key=lambda item: (item["p_value"], -item["pivot_hits"], item["feature"]))
    return rows[:top_n]


def run_candidate(
    name: str,
    birth_dt: datetime,
    daily_df: pd.DataFrame,
    pivot_dates: set[pd.Timestamp],
    transit_cache: dict[pd.Timestamp, dict[str, float]],
    orb_deg: float,
    min_support: int,
    top_n: int,
) -> CandidateResult:
    print(f"\n{'=' * 90}")
    print(f"КАНДИДАТ НАТАЛА: {name} ({birth_dt.isoformat(sep=' ')})")
    print(f"{'=' * 90}")

    natal_positions = build_natal_positions(birth_dt)
    print("  Натальные позиции:")
    for body_name, lon in natal_positions.items():
        print(f"    {body_name:<9} {lon:>7.2f}°")

    feature_df = build_feature_frame(daily_df, pivot_dates, transit_cache, natal_positions, orb_deg)
    pivots = feature_df[feature_df["is_pivot"]]
    baseline = feature_df[~feature_df["is_pivot"]]

    _, mw_p = stats.mannwhitneyu(
        pivots["natal_hit_count"],
        baseline["natal_hit_count"],
        alternative="greater",
    )

    print(f"\n  Pivot days: {len(pivots)}")
    print(f"  Baseline days: {len(baseline)}")
    print(f"  Средний natal_hit_count на pivot-днях: {pivots['natal_hit_count'].mean():.2f}")
    print(f"  Средний natal_hit_count на baseline:   {baseline['natal_hit_count'].mean():.2f}")
    print(f"  Mann-Whitney p-value: {mw_p:.4f}")

    saturn_pivots = pivots["saturn_to_natal_saturn_orb"].to_numpy()
    saturn_base = baseline["saturn_to_natal_saturn_orb"].to_numpy()
    _, saturn_p = stats.mannwhitneyu(saturn_pivots, saturn_base, alternative="less")
    print(f"  Saturn→нат.Saturn orb, pivot vs baseline: p={saturn_p:.4f}")

    rows = evaluate_features(feature_df, min_support=min_support, top_n=top_n)

    print(f"\n  Топ natal-transit признаков (support >= {min_support}):")
    if not rows:
        print("    Нет признаков с достаточной частотой.")
    else:
        print(f"    {'Признак':<38} {'Pivot%':>8} {'Base%':>8} {'Lift':>8} {'p':>8} {'q':>8}")
        for item in rows:
            q_value = item.get("q_value")
            q_text = f"{q_value:.4f}" if isinstance(q_value, float) else "—"
            lift_text = f"{item['lift']:.2f}" if item["lift"] is not None else "inf"
            print(
                f"    {item['feature']:<38} {item['pivot_pct']:>7.1f}% {item['baseline_pct']:>7.1f}% "
                f"{lift_text:>8} {item['p_value']:>8.4f} {q_text:>8}"
            )

    return CandidateResult(
        name=name,
        birth_dt=birth_dt,
        pivot_count=len(pivots),
        baseline_count=len(baseline),
        pivot_hit_mean=float(pivots["natal_hit_count"].mean()),
        baseline_hit_mean=float(baseline["natal_hit_count"].mean()),
        mw_p_value=float(mw_p),
        key_feature_rows=rows,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Проверка теории натальной карты BTC на исторических pivot-днях.")
    parser.add_argument(
        "--birth",
        action="append",
        default=[],
        help=(
            "Кандидат натала в формате name=YYYY-MM-DDTHH:MM:SS. "
            "Если не передан, прогоняется default basket из нескольких BTC timestamps."
        ),
    )
    parser.add_argument("--start", default="2016-01-01", help="Начало периода анализа YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="Конец периода анализа YYYY-MM-DD")
    parser.add_argument("--orb", type=float, default=3.0, help="Орб для аспектов к наталу в градусах")
    parser.add_argument("--min-support", type=int, default=4, help="Минимум pivot-попаданий для вывода признака")
    parser.add_argument("--top", type=int, default=15, help="Сколько top-признаков показать")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    birth_specs = args.birth or DEFAULT_BIRTH_SPECS
    candidates = parse_birth_specs(birth_specs)

    print("Загрузка рыночных данных...")
    daily_df, pivot_dates = load_market_data(args.start, args.end)
    if daily_df.empty:
        raise SystemExit("Нет данных в btc_daily для выбранного периода.")
    if not pivot_dates:
        raise SystemExit("Нет pivot-дней в btc_pivots для выбранного периода.")

    print(f"Дней в истории: {len(daily_df)}")
    print(f"Pivot-дней: {len(pivot_dates)}")
    print("Построение cache транзитов...")
    transit_cache = build_transit_cache(daily_df)

    results = []
    for name, birth_dt in candidates:
        results.append(
            run_candidate(
                name=name,
                birth_dt=birth_dt,
                daily_df=daily_df,
                pivot_dates=pivot_dates,
                transit_cache=transit_cache,
                orb_deg=args.orb,
                min_support=args.min_support,
                top_n=args.top,
            )
        )

    if len(results) > 1:
        print(f"\n{'=' * 90}")
        print("СРАВНЕНИЕ КАНДИДАТОВ НАТАЛА")
        print(f"{'=' * 90}")
        print(f"{'Кандидат':<24} {'Pivot hits':>12} {'Base hits':>12} {'MW p-value':>12}")
        for item in sorted(results, key=lambda row: row.mw_p_value):
            print(
                f"{item.name:<24} {item.pivot_hit_mean:>12.2f} {item.baseline_hit_mean:>12.2f} "
                f"{item.mw_p_value:>12.4f}"
            )


if __name__ == "__main__":
    main()
