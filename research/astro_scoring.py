"""
BTC Астро-скоринг: модель вероятности разворота.
Строит балл для любой даты на основе найденных корреляций.
Проверяет на исторических данных + генерирует календарь.
"""

import sqlite3
import ephem
import math
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from astro_shared import (
    DB_PATH,
    ECLIPSE_DATES,
    ELEMENT_MAP,
    MAJOR_TRANSIT_DATES,
    MODALITY_MAP,
    RETROGRADES_KNOWN,
    ZODIAC_SIGNS,
    get_zodiac_sign,
    today_local_date,
)


# ============================================================
# АСТРО-РАСЧЁТЫ (из extended_analysis)
# ============================================================

def _get_ecliptic_lon(body):
    return float(ephem.Ecliptic(body).lon) * 180 / math.pi

def _is_retrograde(planet_class, d_now, d_prev):
    lon_now = _get_ecliptic_lon(planet_class(d_now))
    lon_prev = _get_ecliptic_lon(planet_class(d_prev))
    diff = lon_now - lon_prev
    if diff > 180: diff -= 360
    elif diff < -180: diff += 360
    return diff < 0

def _is_stationary(planet_class, d_now, orb_days=2):
    d_before = ephem.Date(d_now - orb_days)
    d_after = ephem.Date(d_now + orb_days)
    lon_before = _get_ecliptic_lon(planet_class(d_before))
    lon_now = _get_ecliptic_lon(planet_class(d_now))
    lon_after = _get_ecliptic_lon(planet_class(d_after))
    def norm(a, b):
        d = a - b
        if d > 180: d -= 360
        elif d < -180: d += 360
        return d
    d1 = norm(lon_now, lon_before)
    d2 = norm(lon_after, lon_now)
    return (d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)

def _get_lunar_node(d):
    jd = ephem.julian_date(d)
    T = (jd - 2451545.0) / 36525.0
    omega = 125.04452 - 1934.136261 * T + 0.0020708 * T**2 + T**3 / 450000
    omega = omega % 360
    if omega < 0:
        omega += 360
    return omega

def _detect_ingress(planet_class, d, window_hours=12):
    d_before = ephem.Date(d - window_hours / 24.0)
    d_after = ephem.Date(d + window_hours / 24.0)
    sign_before = get_zodiac_sign(_get_ecliptic_lon(planet_class(d_before)))
    sign_now = get_zodiac_sign(_get_ecliptic_lon(planet_class(d)))
    sign_after = get_zodiac_sign(_get_ecliptic_lon(planet_class(d_after)))
    if sign_before != sign_now:
        return True, sign_now
    if sign_now != sign_after:
        return True, sign_after
    return False, None

def _days_to_nearest_phase(d):
    """Дней до ближайшего новолуния и полнолуния."""
    prev_new = ephem.previous_new_moon(d)
    next_new = ephem.next_new_moon(d)
    dist_new = min(abs(d - prev_new), abs(next_new - d))
    prev_full = ephem.previous_full_moon(d)
    next_full = ephem.next_full_moon(d)
    dist_full = min(abs(d - prev_full), abs(next_full - d))
    return float(dist_new), float(dist_full)


# ============================================================
# СКОРИНГОВАЯ МОДЕЛЬ
# ============================================================

def compute_score(date):
    """
    Астро-скоринг для даты.
    Возвращает (total_score, details, direction_bias).
    direction_bias: >0 → скорее пик, <0 → скорее дно.
    """
    d = ephem.Date(date)
    d_prev = ephem.Date(date - timedelta(days=1))
    moon = ephem.Moon(d)

    score = 0.0
    direction = 0.0  # >0 пик, <0 дно
    details = []

    # === 1. Новолуние / Полнолуние (±2д) — ratio 1.42x ===
    dist_new, dist_full = _days_to_nearest_phase(d)
    dist_phase = min(dist_new, dist_full)

    if dist_phase <= 1:
        score += 2.0
        phase_name = "новолуние" if dist_new < dist_full else "полнолуние"
        details.append(f"+2.0  ±1д от {phase_name} ({dist_phase:.1f}д)")
    elif dist_phase <= 2:
        score += 1.0
        phase_name = "новолуние" if dist_new < dist_full else "полнолуние"
        details.append(f"+1.0  ±2д от {phase_name} ({dist_phase:.1f}д)")

    # Четверти — антисигнал
    prev_fq = ephem.previous_first_quarter_moon(d)
    next_fq = ephem.next_first_quarter_moon(d)
    prev_lq = ephem.previous_last_quarter_moon(d)
    next_lq = ephem.next_last_quarter_moon(d)
    dist_fq = min(abs(d - prev_fq), abs(next_fq - d))
    dist_lq = min(abs(d - prev_lq), abs(next_lq - d))
    dist_quarter = min(float(dist_fq), float(dist_lq))

    if dist_quarter <= 1:
        score -= 1.0
        details.append(f"-1.0  ±1д от четверти Луны (антисигнал)")

    # === 2. Затмение ±7д — ratio 2.25x ===
    min_eclipse = min(abs((date - ed).days) for ed in ECLIPSE_DATES)
    if min_eclipse <= 3:
        score += 3.0
        details.append(f"+3.0  Затмение ±3д ({min_eclipse}д)")
    elif min_eclipse <= 7:
        score += 2.0
        details.append(f"+2.0  Затмение ±7д ({min_eclipse}д)")

    # === 3. Ингрессия Луны — ratio 1.38x, пики 1.95x ===
    moon_ingress, new_sign = _detect_ingress(ephem.Moon, d, window_hours=6)
    if moon_ingress:
        score += 1.5
        details.append(f"+1.5  Ингрессия Луны → {new_sign}")
        direction += 1.0  # чаще пики

    # === 4. Ретроградность ===
    planet_classes = {
        "Меркурий": ephem.Mercury, "Венера": ephem.Venus, "Марс": ephem.Mars,
        "Юпитер": ephem.Jupiter, "Сатурн": ephem.Saturn,
    }
    PLANET_NAME_MAP = {
        "Mercury": "Меркурий", "Venus": "Венера", "Mars": "Марс",
        "Jupiter": "Юпитер", "Saturn": "Сатурн", "Uranus": "Уран",
        "Neptune": "Нептун", "Pluto": "Плутон",
    }

    retro_planets = []
    if date.year >= 2026:
        # Справочник ретроградов (проверенные данные из интернета)
        for start_s, end_s, planet_en in RETROGRADES_KNOWN:
            r_start = datetime.strptime(start_s, "%Y-%m-%d")
            r_end = datetime.strptime(end_s, "%Y-%m-%d")
            if r_start <= date <= r_end:
                ru_name = PLANET_NAME_MAP.get(planet_en, planet_en)
                if ru_name not in retro_planets:
                    retro_planets.append(ru_name)
    else:
        for name, cls in planet_classes.items():
            if _is_retrograde(cls, d, d_prev):
                retro_planets.append(name)

    mars_retro = "Марс" in retro_planets
    jupiter_retro = "Юпитер" in retro_planets

    # Марс ретро + затмение — ratio 4.86x
    if mars_retro and min_eclipse <= 7:
        score += 2.0
        details.append(f"+2.0  Марс ретро + затмение (4.86x)")

    # Марс + Юпитер ретро вместе — ratio 1.96x
    if mars_retro and jupiter_retro:
        score += 1.0
        details.append(f"+1.0  Марс + Юпитер ретро")

    # Много ретро (≥2)
    if len(retro_planets) >= 2:
        score += 0.5
        details.append(f"+0.5  {len(retro_planets)} ретро планет ({', '.join(retro_planets)})")

    # Много ретро (≥4) — редкое событие, дополнительный бонус
    if len(retro_planets) >= 4:
        score += 1.0
        details.append(f"+1.0  Массовый ретроград ({len(retro_planets)} планет)")

    # === 4b. Крупные планетарные транзиты ===
    for transit_date, transit_desc in MAJOR_TRANSIT_DATES.items():
        days_diff = abs((date - transit_date).days)
        if days_diff <= 3:
            # Соединение Сатурн-Нептун — раз в 36 лет, максимальный бонус
            if "Сатурн-Нептун" in transit_desc:
                score += 3.0
                details.append(f"+3.0  {transit_desc} (±{days_diff}д, раз в 36 лет!)")
            # Трины Уран-Плутон — раз в 140 лет
            elif "Уран-Плутон" in transit_desc:
                score += 2.0
                details.append(f"+2.0  {transit_desc} (±{days_diff}д)")
            # Ингрессии планет в новый знак
            else:
                score += 1.5
                details.append(f"+1.5  {transit_desc} (±{days_diff}д)")
        elif days_diff <= 7:
            if "Сатурн-Нептун" in transit_desc:
                score += 2.0
                details.append(f"+2.0  {transit_desc} (±{days_diff}д)")
            elif "Уран-Плутон" in transit_desc:
                score += 1.0
                details.append(f"+1.0  {transit_desc} (±{days_diff}д)")
            else:
                score += 0.5
                details.append(f"+0.5  {transit_desc} (±{days_diff}д)")

    # === 5. Стационарные планеты ===
    station_planets = []
    for name, cls in planet_classes.items():
        if _is_stationary(cls, d):
            station_planets.append(name)

    if station_planets:
        score += 1.5
        details.append(f"+1.5  Стационарные: {', '.join(station_planets)}")
        direction -= 1.0  # чаще дно

    # === 6. Аспекты к лунным узлам ===
    moon_lon = _get_ecliptic_lon(moon)
    rahu_lon = _get_lunar_node(d)
    ketu_lon = (rahu_lon + 180) % 360

    moon_rahu = abs(moon_lon - rahu_lon)
    if moon_rahu > 180: moon_rahu = 360 - moon_rahu

    # Луна-квадратура-узлов — 1.82x
    if abs(moon_rahu - 90) <= 8 or moon_rahu <= 10:
        score += 1.0
        if moon_rahu <= 10:
            details.append(f"+1.0  Луна-конъюнкция-Раху ({moon_rahu:.0f}°)")
        else:
            details.append(f"+1.0  Луна-квадратура-узлов ({moon_rahu:.0f}°)")

    # Сатурн-квадратура-узлов — 1.59x
    saturn_lon = _get_ecliptic_lon(ephem.Saturn(d))
    sat_rahu = abs(saturn_lon - rahu_lon)
    if sat_rahu > 180: sat_rahu = 360 - sat_rahu
    if abs(sat_rahu - 90) <= 8:
        score += 0.5
        details.append(f"+0.5  Сатурн-квадратура-узлов")

    # === 7. Напряжённые аспекты ===
    bodies = {
        "Луна": moon_lon,
        "Солнце": _get_ecliptic_lon(ephem.Sun(d)),
        "Меркурий": _get_ecliptic_lon(ephem.Mercury(d)),
        "Венера": _get_ecliptic_lon(ephem.Venus(d)),
        "Марс": _get_ecliptic_lon(ephem.Mars(d)),
        "Юпитер": _get_ecliptic_lon(ephem.Jupiter(d)),
        "Сатурн": saturn_lon,
    }

    tension = 0
    harmony = 0
    body_names = list(bodies.keys())
    for i in range(len(body_names)):
        for j in range(i + 1, len(body_names)):
            diff = abs(bodies[body_names[i]] - bodies[body_names[j]])
            if diff > 180: diff = 360 - diff
            if abs(diff - 90) <= 8 or abs(diff - 180) <= 8:
                tension += 1
            elif abs(diff - 120) <= 8 or abs(diff - 60) <= 6:
                harmony += 1

    if tension >= 3:
        score += 1.0
        details.append(f"+1.0  Высокое напряжение ({tension} аспектов)")

    # === 8. Направление (пик vs дно) ===
    moon_sign = get_zodiac_sign(moon_lon)
    moon_element = ELEMENT_MAP[moon_sign]
    moon_modality = MODALITY_MAP[moon_sign]

    # Вода → пики (+16.8% перекос)
    if moon_element == "Вода":
        direction += 1.5
        details.append(f"  ↑ Луна в Воде ({moon_sign}) → скорее пик")
    # Земля → дно (+11.3% перекос)
    elif moon_element == "Земля":
        direction -= 1.0
        details.append(f"  ↓ Луна в Земле ({moon_sign}) → скорее дно")

    # Мутабельный → пики (+10%)
    if moon_modality == "Мутабельный":
        direction += 0.5
    elif moon_modality == "Кардинальный":
        direction -= 0.5

    # Фаза Луны
    prev_new_moon = ephem.previous_new_moon(d)
    next_new_moon = ephem.next_new_moon(d)
    cycle_len = next_new_moon - prev_new_moon
    position = (d - prev_new_moon) / cycle_len

    if position < 0.125 or position >= 0.875:
        quarter = "Новолуние"
    elif 0.125 <= position < 0.375:
        quarter = "Растущая"
    elif 0.375 <= position < 0.625:
        quarter = "Полнолуние"
    else:
        quarter = "Убывающая"

    return {
        "score": round(score, 1),
        "direction": round(direction, 1),
        "details": details,
        "moon_sign": moon_sign,
        "moon_element": moon_element,
        "quarter": quarter,
        "retro_planets": retro_planets,
        "station_planets": station_planets,
        "eclipse_days": min_eclipse,
        "moon_ingress": moon_ingress,
        "tension": tension,
        "harmony": harmony,
    }


# ============================================================
# ВАЛИДАЦИЯ НА ИСТОРИЧЕСКИХ ДАННЫХ
# ============================================================

def load_historical_data():
    conn = sqlite3.connect(DB_PATH)
    pivots = pd.read_sql("""
        SELECT date, price, type, pct_change
        FROM btc_pivots
        ORDER BY date
    """, conn)
    all_days = pd.read_sql("""
        SELECT date, close
        FROM btc_daily
        ORDER BY date
    """, conn)
    conn.close()

    pivots["date"] = pd.to_datetime(pivots["date"])
    all_days["date"] = pd.to_datetime(all_days["date"])
    return pivots, all_days


def build_history_scores(all_days: pd.DataFrame) -> pd.DataFrame:
    print("\nПодсчёт астроскоров для всей истории...")
    records = []

    for idx, row in all_days.iterrows():
        result = compute_score(row["date"].to_pydatetime())
        result["date"] = row["date"]
        result["close"] = row["close"]
        records.append(result)

        if (idx + 1) % 250 == 0:
            print(f"  {idx + 1}/{len(all_days)} дней...")

    return pd.DataFrame(records).sort_values("date").reset_index(drop=True)


def assign_sample_split(history_df: pd.DataFrame, test_ratio: float = 0.20) -> tuple[pd.DataFrame, pd.Timestamp]:
    history_df = history_df.sort_values("date").reset_index(drop=True).copy()
    if len(history_df) < 2:
        history_df["sample_split"] = "test"
        return history_df, history_df["date"].iloc[0]

    split_idx = max(1, int(len(history_df) * (1 - test_ratio)))
    split_idx = min(split_idx, len(history_df) - 1)
    split_start = history_df.loc[split_idx, "date"]
    history_df["sample_split"] = np.where(history_df["date"] >= split_start, "test", "train")
    return history_df, split_start


def build_pivot_scores(pivots: pd.DataFrame, history_df: pd.DataFrame) -> pd.DataFrame:
    score_cols = [
        "date",
        "score",
        "direction",
        "sample_split",
        "moon_sign",
        "moon_element",
        "quarter",
        "eclipse_days",
        "moon_ingress",
        "tension",
        "harmony",
    ]
    pdf = pivots.merge(history_df[score_cols], on="date", how="left", validate="many_to_one")
    pdf["is_high"] = pdf["type"].str.contains("high")
    pdf["is_major"] = pdf["type"].str.contains("major|global")
    return pdf


def print_validation_block(label: str, pdf: pd.DataFrame, base_arr: np.ndarray) -> dict:
    print(f"\n  --- {label} ---")
    print(f"  Разворотов: {len(pdf)}, непивотных дней: {len(base_arr)}")

    if len(pdf) == 0 or len(base_arr) == 0:
        print("  Недостаточно данных для статистики.")
        return {
            "pivot_count": len(pdf),
            "base_count": len(base_arr),
            "avg_score": 0.0,
            "pivot_avg_score": 0.0,
            "direction_accuracy": 0.0,
            "thresholds": [],
        }

    print(f"  {'':>20} {'Развороты':>12} {'Непивотные':>12}")
    print(f"  {'Среднее':<20} {pdf['score'].mean():>12.2f} {base_arr.mean():>12.2f}")
    print(f"  {'Медиана':<20} {pdf['score'].median():>12.2f} {np.median(base_arr):>12.2f}")
    print(f"  {'Макс':<20} {pdf['score'].max():>12.1f} {base_arr.max():>12.1f}")
    print(f"  {'Мин':<20} {pdf['score'].min():>12.1f} {base_arr.min():>12.1f}")

    t_stat, p_value = stats.ttest_ind(pdf["score"], base_arr, equal_var=False)
    print(f"\n  Welch t-test: t={t_stat:.3f}, p={p_value:.4f}")

    _, p_mw = stats.mannwhitneyu(pdf["score"], base_arr, alternative="greater")
    print(f"  Mann-Whitney U: p={p_mw:.4f}")

    print(f"\n  {'Порог':>8} {'Разворотов':>12} {'Pivot%':>8} {'Base%':>8} {'Lift':>8} {'Precision':>10}")
    thresholds = []
    for threshold in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]:
        p_above = int((pdf["score"] >= threshold).sum())
        b_above = float((base_arr >= threshold).mean() * 100)
        p_pct = p_above / len(pdf) * 100

        if b_above > 0:
            lift = p_pct / b_above
        else:
            lift = float("inf") if p_above > 0 else 0.0

        total_days_above = int((base_arr >= threshold).sum())
        precision = p_above / max(p_above + total_days_above, 1) * 100
        thresholds.append({
            "threshold": threshold,
            "pivots_above": p_above,
            "pivot_pct": round(p_pct, 1),
            "base_pct": round(b_above, 1),
            "lift": round(lift, 2) if lift != float("inf") else float("inf"),
            "precision": round(precision, 1),
        })

        print(f"  {threshold:>6.0f}+ {p_above:>6}/{len(pdf):>3} {p_pct:>6.1f}% {b_above:>6.1f}% "
              f"{lift:>7.2f}x {precision:>8.1f}%")

    highs = pdf[pdf["is_high"]]
    lows = pdf[~pdf["is_high"]]
    correct_dir = int((highs["direction"] > 0).sum() + (lows["direction"] < 0).sum())
    total_with_dir = int((highs["direction"] != 0).sum() + (lows["direction"] != 0).sum())
    direction_accuracy = correct_dir / total_with_dir * 100 if total_with_dir else 0.0

    print(f"\n  Пики ({len(highs)}): ср. скор = {highs['score'].mean():.2f}, ср. direction = {highs['direction'].mean():.2f}")
    print(f"  Дно ({len(lows)}): ср. скор = {lows['score'].mean():.2f}, ср. direction = {lows['direction'].mean():.2f}")
    if total_with_dir:
        print(f"  Точность направления: {correct_dir}/{total_with_dir} ({direction_accuracy:.1f}%)")

    top = pdf.nlargest(10, "score")
    if len(top) > 0:
        print(f"\n  Топ-10 разворотов по скору ({label}):")
        for _, row in top.iterrows():
            dir_arrow = "↑ пик" if row["direction"] > 0 else "↓ дно" if row["direction"] < 0 else "—"
            print(
                f"  {row['date'].strftime('%Y-%m-%d')}  ${row['price']:>9,.0f}  "
                f"{row['type']:<15} скор={row['score']:>4.1f}  {dir_arrow}"
            )

    return {
        "pivot_count": len(pdf),
        "base_count": len(base_arr),
        "avg_score": round(float(base_arr.mean()), 2),
        "pivot_avg_score": round(float(pdf["score"].mean()), 2),
        "direction_accuracy": round(direction_accuracy, 1),
        "thresholds": thresholds,
    }


def validate_model():
    print("=" * 90)
    print("ВАЛИДАЦИЯ СКОРИНГОВОЙ МОДЕЛИ НА ИСТОРИЧЕСКИХ ДАННЫХ")
    print("=" * 90)

    pivots, all_days = load_historical_data()
    history_df = build_history_scores(all_days)
    history_df, split_start = assign_sample_split(history_df)
    history_df["is_pivot"] = history_df["date"].isin(set(pivots["date"]))
    pdf = build_pivot_scores(pivots, history_df)

    print(
        f"\nИстория: {history_df['date'].min().strftime('%Y-%m-%d')} — "
        f"{history_df['date'].max().strftime('%Y-%m-%d')}"
    )
    print(
        f"Holdout split: train < {split_start.strftime('%Y-%m-%d')}, "
        f"test >= {split_start.strftime('%Y-%m-%d')}"
    )

    train_pdf = pdf[pdf["sample_split"] == "train"].copy()
    train_base = history_df[
        (history_df["sample_split"] == "train") & (~history_df["is_pivot"])
    ]["score"].to_numpy()
    test_pdf = pdf[pdf["sample_split"] == "test"].copy()
    test_base = history_df[
        (history_df["sample_split"] == "test") & (~history_df["is_pivot"])
    ]["score"].to_numpy()

    print_validation_block("TRAIN", train_pdf, train_base)
    test_metrics = print_validation_block("TEST (holdout)", test_pdf, test_base)

    return history_df, test_pdf, test_base, test_metrics


# ============================================================
# АСТРО-КАЛЕНДАРЬ
# ============================================================

def generate_calendar(start_date, end_date):
    print(f"\n\n{'=' * 90}")
    print(f"АСТРО-КАЛЕНДАРЬ BTC: {start_date.strftime('%Y-%m-%d')} — {end_date.strftime('%Y-%m-%d')}")
    print(f"{'=' * 90}")

    days = []
    current = start_date
    while current <= end_date:
        result = compute_score(current)
        result["date"] = current
        days.append(result)
        current += timedelta(days=1)

    df = pd.DataFrame(days)

    # Зоны повышенного риска (score >= 3)
    hot_zones = df[df["score"] >= 3].copy()

    if len(hot_zones) > 0:
        print(f"\n  ЗОНЫ ПОВЫШЕННОГО РИСКА РАЗВОРОТА (скор ≥ 3):")
        print(f"  {'Дата':<12} {'Скор':>5} {'Направл.':>10} {'Луна':>15} {'Детали'}")
        print("  " + "-" * 85)

        for _, row in hot_zones.iterrows():
            dir_str = "↑ скорее пик" if row["direction"] > 0 else "↓ скорее дно" if row["direction"] < 0 else "нейтрально"
            moon_info = f"{row['quarter'][:4]} {row['moon_sign']}"
            detail_short = "; ".join(d.strip().split("  ")[-1][:40] for d in row["details"] if d.startswith("+"))
            print(f"  {row['date'].strftime('%Y-%m-%d'):<12} {row['score']:>5.1f} "
                  f"{dir_str:>12} {moon_info:>15}  {detail_short[:50]}")
    else:
        print(f"\n  Зон с высоким скором не найдено в этом периоде.")

    # Кластеры (группируем дни подряд)
    print(f"\n\n  КЛАСТЕРЫ (дни подряд с score ≥ 2):")
    cluster_days = df[df["score"] >= 2]
    if len(cluster_days) > 0:
        clusters = []
        current_cluster = []
        for _, row in cluster_days.iterrows():
            if not current_cluster or (row["date"] - current_cluster[-1]["date"]).days <= 2:
                current_cluster.append(row)
            else:
                if len(current_cluster) >= 1:
                    clusters.append(current_cluster)
                current_cluster = [row]
        if current_cluster:
            clusters.append(current_cluster)

        for cluster in clusters:
            start = cluster[0]["date"]
            end = cluster[-1]["date"]
            max_score = max(c["score"] for c in cluster)
            avg_dir = np.mean([c["direction"] for c in cluster])
            dir_str = "↑ ПИК" if avg_dir > 0.5 else "↓ ДНО" if avg_dir < -0.5 else "?"

            if (end - start).days == 0:
                print(f"  {start.strftime('%Y-%m-%d'):>12}           макс={max_score:.1f}  {dir_str}")
            else:
                print(f"  {start.strftime('%Y-%m-%d')} — {end.strftime('%Y-%m-%d')}  макс={max_score:.1f}  {dir_str}")

    # Месячная сводка
    print(f"\n\n  МЕСЯЧНАЯ СВОДКА:")
    df["month"] = df["date"].apply(lambda x: x.strftime("%Y-%m"))
    monthly = df.groupby("month").agg(
        avg_score=("score", "mean"),
        max_score=("score", "max"),
        hot_days=("score", lambda x: (x >= 3).sum()),
    ).reset_index()

    print(f"  {'Месяц':<10} {'Ср. скор':>10} {'Макс':>6} {'Горячих дней':>14}")
    for _, row in monthly.iterrows():
        bar = "█" * int(row["hot_days"])
        print(f"  {row['month']:<10} {row['avg_score']:>10.2f} {row['max_score']:>6.1f} {int(row['hot_days']):>10}  {bar}")

    return df


# ============================================================
# ВИЗУАЛИЗАЦИЯ
# ============================================================

def plot_results(pdf, base_arr, calendar_df):
    fig, axes = plt.subplots(2, 2, figsize=(22, 14))

    # 1. Распределение скоров: развороты vs baseline
    ax = axes[0, 0]
    bins = np.arange(0, max(pdf["score"].max(), base_arr.max()) + 1, 0.5)
    ax.hist(base_arr, bins=bins, color="#4ECDC4", alpha=0.6, label="Непивотные дни (holdout)", edgecolor="black", linewidth=0.3,
            weights=np.ones(len(base_arr)) * len(pdf) / len(base_arr))
    ax.hist(pdf["score"], bins=bins, color="#FF6B6B", alpha=0.7, label="Развороты (holdout)", edgecolor="black", linewidth=0.3)
    ax.set_xlabel("Астро-скор")
    ax.set_ylabel("Кол-во")
    ax.set_title("Распределение скоров: holdout развороты vs непивотные дни", fontweight="bold")
    ax.legend()
    ax.axvline(x=3, color="red", linestyle="--", alpha=0.5, label="Порог ≥3")

    # 2. Score timeline + пики/дно
    ax = axes[0, 1]
    highs = pdf[pdf["is_high"]]
    lows = pdf[~pdf["is_high"]]
    ax.scatter(highs["date"], highs["score"], c="red", s=60, label="Пики", edgecolors="black", linewidths=0.3, zorder=3)
    ax.scatter(lows["date"], lows["score"], c="green", s=60, label="Дно", edgecolors="black", linewidths=0.3, zorder=3)
    ax.axhline(y=3, color="orange", linestyle="--", alpha=0.5, label="Порог ≥3")
    ax.set_xlabel("Дата")
    ax.set_ylabel("Астро-скор")
    ax.set_title("Скор разворотов по времени (holdout-период)", fontweight="bold")
    ax.legend(fontsize=8)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))

    # 3. Direction: пики vs дно
    ax = axes[1, 0]
    ax.scatter(highs["direction"], highs["score"], c="red", s=60, label="Пики", edgecolors="black", linewidths=0.3)
    ax.scatter(lows["direction"], lows["score"], c="green", s=60, label="Дно", edgecolors="black", linewidths=0.3)
    ax.axvline(x=0, color="gray", linestyle="-", linewidth=0.5)
    ax.axhline(y=3, color="orange", linestyle="--", alpha=0.5)
    ax.set_xlabel("Direction bias (>0 = пик, <0 = дно)")
    ax.set_ylabel("Астро-скор")
    ax.set_title("Скор vs Направление", fontweight="bold")
    ax.legend()

    # 4. Астро-календарь
    ax = axes[1, 1]
    cal_dates = [d for d in calendar_df["date"]]
    cal_scores = list(calendar_df["score"])
    colors = ["#FF6B6B" if s >= 3 else "#FFC107" if s >= 2 else "#4ECDC4" for s in cal_scores]
    ax.bar(cal_dates, cal_scores, color=colors, edgecolor="none", width=1.0)
    ax.axhline(y=3, color="red", linestyle="--", alpha=0.5, label="Порог ≥3")
    ax.axhline(y=2, color="orange", linestyle="--", alpha=0.3, label="Порог ≥2")
    ax.set_xlabel("Дата")
    ax.set_ylabel("Астро-скор")
    ax.set_title("Астро-календарь (красный = зоны риска)", fontweight="bold")
    ax.legend(fontsize=8)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

    plt.suptitle("BTC Астро-скоринг — Модель + Календарь",
                 fontsize=16, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig("astro_scoring_results.png", dpi=150, bbox_inches="tight")
    print("\nГрафик: astro_scoring_results.png")
    plt.close()


# ============================================================
# СОХРАНЕНИЕ В БД
# ============================================================

def save_calendar_to_db(calendar_df):
    conn = sqlite3.connect(DB_PATH)
    rows = []
    for _, row in calendar_df.iterrows():
        rows.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "score": row["score"],
            "direction": row["direction"],
            "moon_sign": row["moon_sign"],
            "moon_element": row["moon_element"],
            "quarter": row["quarter"],
            "eclipse_days": row["eclipse_days"],
            "moon_ingress": int(row["moon_ingress"]),
            "tension": row["tension"],
            "harmony": row["harmony"],
            "retro_planets": ",".join(row["retro_planets"]),
            "station_planets": ",".join(row["station_planets"]),
            "details": " | ".join(row["details"]),
        })
    df = pd.DataFrame(rows)
    df.to_sql("btc_astro_calendar", conn, if_exists="replace", index=False)
    print(f"Сохранено в btc_astro_calendar: {len(df)} строк")
    conn.close()


def save_history_to_db(history_df):
    conn = sqlite3.connect(DB_PATH)
    rows = []
    for _, row in history_df.iterrows():
        rows.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "close": row["close"],
            "score": row["score"],
            "direction": row["direction"],
            "moon_sign": row["moon_sign"],
            "moon_element": row["moon_element"],
            "quarter": row["quarter"],
            "eclipse_days": row["eclipse_days"],
            "moon_ingress": int(row["moon_ingress"]),
            "tension": row["tension"],
            "harmony": row["harmony"],
            "retro_planets": ",".join(row["retro_planets"]),
            "station_planets": ",".join(row["station_planets"]),
            "details": " | ".join(row["details"]),
            "sample_split": row["sample_split"],
            "is_pivot": int(row["is_pivot"]),
        })

    df = pd.DataFrame(rows)
    df.to_sql("btc_astro_history", conn, if_exists="replace", index=False)
    print(f"Сохранено в btc_astro_history: {len(df)} строк")
    conn.close()


def main():
    # 1. Валидация на истории
    history_df, pdf, base_arr, _ = validate_model()

    # 2. Календарь до конца 2028
    today = datetime.combine(today_local_date(), datetime.min.time())
    end_date = datetime(2028, 12, 31)
    calendar_df = generate_calendar(today, end_date)

    # 3. Визуализация
    plot_results(pdf, base_arr, calendar_df)

    # 4. Сохранение
    save_history_to_db(history_df)
    save_calendar_to_db(calendar_df)

    # 5. Ближайшие горячие зоны
    print(f"\n\n{'=' * 90}")
    print("БЛИЖАЙШИЕ ЗОНЫ РИСКА РАЗВОРОТА")
    print("=" * 90)

    hot = calendar_df[calendar_df["score"] >= 3].head(15)
    for _, row in hot.iterrows():
        dir_str = "↑ ПИК" if row["direction"] > 0 else "↓ ДНО" if row["direction"] < 0 else "  ?"
        days_away = (row["date"] - today).days
        print(f"\n  {row['date'].strftime('%Y-%m-%d')} (через {days_away}д)  СКОР: {row['score']:.1f}  {dir_str}")
        print(f"    {row['quarter']} | Луна в {row['moon_sign']} ({row['moon_element']})")
        for d in row["details"]:
            print(f"    {d}")


if __name__ == "__main__":
    main()
