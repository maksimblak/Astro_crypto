"""
BTC x Астрология: Анализ разворотных точек
Какие астро-условия были в моменты каждого пика и дна?
Находим паттерны которые чаще совпадают с разворотами.
"""
import os

import sqlite3
import ephem
import math
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy import stats
from collections import Counter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "btc_research.db")

ZODIAC_SIGNS = [
    "Овен", "Телец", "Близнецы", "Рак",
    "Лев", "Дева", "Весы", "Скорпион",
    "Стрелец", "Козерог", "Водолей", "Рыбы"
]

ECLIPSES = [
    ("2020-01-10", "lunar"), ("2020-06-05", "lunar"), ("2020-06-21", "solar"),
    ("2020-07-05", "lunar"), ("2020-11-30", "lunar"), ("2020-12-14", "solar"),
    ("2021-05-26", "lunar"), ("2021-06-10", "solar"), ("2021-11-19", "lunar"),
    ("2021-12-04", "solar"), ("2022-04-30", "solar"), ("2022-05-16", "lunar"),
    ("2022-10-25", "solar"), ("2022-11-08", "lunar"), ("2023-04-20", "solar"),
    ("2023-05-05", "lunar"), ("2023-10-14", "solar"), ("2023-10-28", "lunar"),
    ("2024-03-25", "lunar"), ("2024-04-08", "solar"), ("2024-09-18", "lunar"),
    ("2024-10-02", "solar"), ("2025-03-14", "lunar"), ("2025-03-29", "solar"),
    ("2025-09-07", "lunar"), ("2025-09-21", "solar"), ("2026-02-17", "solar"),
    ("2026-03-03", "lunar"),
]
ECLIPSE_DATES = [datetime.strptime(e[0], "%Y-%m-%d") for e in ECLIPSES]


def get_zodiac_sign(lon_deg):
    return ZODIAC_SIGNS[int(lon_deg / 30) % 12]


def _is_retrograde(planet_class, d_now, d_prev):
    """Определяет ретроградность планеты по изменению эклиптической долготы."""
    body_now = planet_class(d_now)
    body_prev = planet_class(d_prev)
    lon_now = float(ephem.Ecliptic(body_now).lon)
    lon_prev = float(ephem.Ecliptic(body_prev).lon)
    diff = lon_now - lon_prev
    if diff > math.pi:
        diff -= 2 * math.pi
    elif diff < -math.pi:
        diff += 2 * math.pi
    return diff < 0


def get_astro_for_date(date):
    """Полный астро-профиль для конкретной даты."""
    d = ephem.Date(date)
    moon = ephem.Moon(d)

    # Фаза Луны
    phase = moon.phase / 100.0
    prev_new = ephem.previous_new_moon(d)
    next_new = ephem.next_new_moon(d)
    cycle_len = next_new - prev_new
    position = (d - prev_new) / cycle_len

    if position < 0.125 or position >= 0.875:
        quarter = "Новолуние"
    elif 0.125 <= position < 0.375:
        quarter = "Растущая"
    elif 0.375 <= position < 0.625:
        quarter = "Полнолуние"
    else:
        quarter = "Убывающая"

    # Знак Луны
    moon_lon = float(ephem.Ecliptic(moon).lon) * 180 / math.pi
    moon_sign = get_zodiac_sign(moon_lon)

    # Ретроградность планет
    d_prev = ephem.Date(date - timedelta(days=1))
    mercury_retro = _is_retrograde(ephem.Mercury, d, d_prev)
    venus_retro = _is_retrograde(ephem.Venus, d, d_prev)
    mars_retro = _is_retrograde(ephem.Mars, d, d_prev)

    # Знаки планет
    planets = {
        "Солнце": ephem.Sun(d),
        "Марс": ephem.Mars(d),
        "Юпитер": ephem.Jupiter(d),
        "Сатурн": ephem.Saturn(d),
        "Венера": ephem.Venus(d),
    }
    planet_signs = {}
    planet_lons = {}
    for name, body in planets.items():
        lon = float(ephem.Ecliptic(body).lon) * 180 / math.pi
        planet_signs[name] = get_zodiac_sign(lon)
        planet_lons[name] = lon

    # Аспекты
    aspect_defs = {
        "соединение": (0, 8),
        "секстиль": (60, 6),
        "квадратура": (90, 8),
        "трин": (120, 8),
        "оппозиция": (180, 8),
    }
    all_bodies = {"Луна": moon_lon, **planet_lons}
    aspects = []
    body_names = list(all_bodies.keys())
    for i in range(len(body_names)):
        for j in range(i + 1, len(body_names)):
            b1, b2 = body_names[i], body_names[j]
            d_angle = abs(all_bodies[b1] - all_bodies[b2])
            if d_angle > 180:
                d_angle = 360 - d_angle
            for asp_name, (angle, orb) in aspect_defs.items():
                if abs(d_angle - angle) <= orb:
                    aspects.append(f"{b1}-{b2} {asp_name}")

    # Близость к затмению
    min_eclipse_days = min(abs((date - ed).days) for ed in ECLIPSE_DATES)

    return {
        "moon_phase": round(phase, 3),
        "moon_quarter": quarter,
        "moon_sign": moon_sign,
        "mercury_retro": mercury_retro,
        "venus_retro": venus_retro,
        "mars_retro": mars_retro,
        "sun_sign": planet_signs["Солнце"],
        "jupiter_sign": planet_signs["Юпитер"],
        "saturn_sign": planet_signs["Сатурн"],
        "eclipse_days": min_eclipse_days,
        "near_eclipse": min_eclipse_days <= 7,
        "aspects": aspects,
        "n_aspects": len(aspects),
        "has_square": any("квадратура" in a for a in aspects),
        "has_opposition": any("оппозиция" in a for a in aspects),
        "has_conjunction": any("соединение" in a for a in aspects),
        "has_trine": any("трин" in a for a in aspects),
    }


def load_pivots():
    """Загружает точки разворота из БД."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("""
        SELECT date, price, type, pct_change
        FROM btc_pivots
        WHERE date >= '2020-01-01'
        ORDER BY date
    """, conn)
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_all_days():
    """Загружает все торговые дни для сравнения (baseline)."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("""
        SELECT date, close FROM btc_daily
        WHERE date >= '2020-01-01'
        ORDER BY date
    """, conn)
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df


def chi_square_test(pivot_counts, baseline_counts, categories):
    """Хи-квадрат тест: распределение в разворотах vs базовое."""
    observed = np.array([pivot_counts.get(c, 0) for c in categories])
    expected_raw = np.array([baseline_counts.get(c, 0) for c in categories])

    if expected_raw.sum() == 0 or observed.sum() == 0:
        return None, None

    # Убираем категории где оба нулевые
    mask = (expected_raw > 0) | (observed > 0)
    if mask.sum() < 2:
        return None, None

    obs = observed[mask]
    exp_raw = expected_raw[mask]
    # Масштабируем expected чтобы sum(expected) == sum(observed)
    expected = exp_raw / exp_raw.sum() * obs.sum()

    chi2, p = stats.chisquare(obs, expected)
    return round(chi2, 3), round(p, 4)


def main():
    pivots = load_pivots()
    all_days_df = load_all_days()

    print(f"Загружено {len(pivots)} точек разворота (с 2020)")
    print(f"Загружено {len(all_days_df)} торговых дней для baseline\n")

    if len(pivots) == 0 or len(all_days_df) == 0:
        print("Недостаточно данных для анализа")
        return

    # Считаем астро для каждого разворота
    print("Вычисление астро-профиля для каждой точки разворота...")
    pivot_astro = []
    for _, row in pivots.iterrows():
        date = row["date"].to_pydatetime()
        astro = get_astro_for_date(date)
        astro["date"] = row["date"]
        astro["price"] = row["price"]
        astro["pivot_type"] = row["type"]
        astro["pct_change"] = row["pct_change"]
        pivot_astro.append(astro)

    pdf = pd.DataFrame(pivot_astro)

    # Baseline: астро для всех дней (сэмплируем каждый 3-й для скорости)
    print("Вычисление baseline астро-данных (каждый 3-й день)...")
    baseline_astro = []
    sampled_days = all_days_df.iloc[::3]
    for _, row in sampled_days.iterrows():
        date = row["date"].to_pydatetime()
        astro = get_astro_for_date(date)
        baseline_astro.append(astro)
        if len(baseline_astro) % 100 == 0:
            print(f"  Baseline: {len(baseline_astro)} дней...")

    bdf = pd.DataFrame(baseline_astro)

    # Разделяем пики и дно
    highs = pdf[pdf["pivot_type"].str.contains("high")]
    lows = pdf[pdf["pivot_type"].str.contains("low")]
    major = pdf[pdf["pivot_type"].str.contains("global|major")]
    local = pdf[pdf["pivot_type"].str.contains("local")]

    print(f"\nПики: {len(highs)}, Дно: {len(lows)}, Major: {len(major)}, Local: {len(local)}")

    # ============================================================
    # ОТЧЁТ
    # ============================================================
    print("\n" + "=" * 90)
    print("BTC РАЗВОРОТЫ x АСТРОЛОГИЯ — АНАЛИЗ КОНКРЕТНЫХ ТОЧЕК (2020-2026)")
    print("=" * 90)

    # --- 1. ФАЗЫ ЛУНЫ ---
    print("\n\n" + "-" * 70)
    print("1. ФАЗЫ ЛУНЫ В МОМЕНТЫ РАЗВОРОТОВ")
    print("-" * 70)

    quarters = ["Новолуние", "Растущая", "Полнолуние", "Убывающая"]
    pivot_q = Counter(pdf["moon_quarter"])
    high_q = Counter(highs["moon_quarter"])
    low_q = Counter(lows["moon_quarter"])
    base_q = Counter(bdf["moon_quarter"])

    chi2, p_chi = chi_square_test(pivot_q, base_q, quarters)

    print(f"\n{'Фаза':<15} {'Все развороты':>14} {'Пики':>8} {'Дно':>8} {'Baseline%':>10}")
    for q in quarters:
        total_pct = pivot_q[q] / len(pdf) * 100
        high_pct = high_q[q] / len(highs) * 100 if len(highs) > 0 else 0
        low_pct = low_q[q] / len(lows) * 100 if len(lows) > 0 else 0
        base_pct = base_q[q] / len(bdf) * 100
        diff = total_pct - base_pct
        marker = " <<<" if abs(diff) > 5 else ""
        print(f"{q:<15} {pivot_q[q]:>5} ({total_pct:>5.1f}%) {high_q[q]:>5} ({high_pct:>4.1f}%) "
              f"{low_q[q]:>5} ({low_pct:>4.1f}%) {base_pct:>8.1f}%{marker}")

    print(f"\n  Хи-квадрат тест (развороты vs baseline): χ²={chi2}, p={p_chi}")

    # --- 2. ЗНАКИ ЛУНЫ ---
    print("\n\n" + "-" * 70)
    print("2. ЗНАКИ ЛУНЫ В МОМЕНТЫ РАЗВОРОТОВ")
    print("-" * 70)

    pivot_signs = Counter(pdf["moon_sign"])
    high_signs = Counter(highs["moon_sign"])
    low_signs = Counter(lows["moon_sign"])
    base_signs = Counter(bdf["moon_sign"])

    chi2_s, p_chi_s = chi_square_test(pivot_signs, base_signs, ZODIAC_SIGNS)

    print(f"\n{'Знак':<12} {'Все':>5} {'Пики':>6} {'Дно':>6} {'Base%':>7} {'Diff':>7}")
    for sign in ZODIAC_SIGNS:
        total = pivot_signs[sign]
        total_pct = total / len(pdf) * 100
        base_pct = base_signs[sign] / len(bdf) * 100
        diff = total_pct - base_pct
        marker = " <<<" if abs(diff) > 3 else ""
        print(f"{sign:<12} {total:>5} ({total_pct:>4.1f}%) {high_signs[sign]:>3}    {low_signs[sign]:>3}    "
              f"{base_pct:>5.1f}%  {diff:>+5.1f}%{marker}")

    print(f"\n  Хи-квадрат: χ²={chi2_s}, p={p_chi_s}")

    # Топ знаков для пиков и дно отдельно
    print("\n  Топ-3 знака Луны при ПИКАХ:", end="  ")
    for sign, cnt in high_signs.most_common(3):
        print(f"{sign}({cnt})", end="  ")
    print("\n  Топ-3 знака Луны при ДНО:", end="    ")
    for sign, cnt in low_signs.most_common(3):
        print(f"{sign}({cnt})", end="  ")
    print()

    # --- 3. РЕТРОГРАДНЫЕ ПЛАНЕТЫ ---
    print("\n\n" + "-" * 70)
    print("3. РЕТРОГРАДНЫЕ ПЛАНЕТЫ В МОМЕНТЫ РАЗВОРОТОВ")
    print("-" * 70)

    for planet, col in [("Меркурий", "mercury_retro"), ("Венера", "venus_retro"), ("Марс", "mars_retro")]:
        retro_pivots = pdf[col].sum()
        retro_highs = highs[col].sum()
        retro_lows = lows[col].sum()
        retro_base = bdf[col].mean() * 100

        retro_pct = retro_pivots / len(pdf) * 100
        diff = retro_pct - retro_base

        # Биномиальный тест
        p_binom = stats.binomtest(int(retro_pivots), len(pdf), bdf[col].mean()).pvalue

        sig = " *" if p_binom < 0.05 else ""
        print(f"\n  {planet} ретро:")
        print(f"    Все развороты: {retro_pivots}/{len(pdf)} ({retro_pct:.1f}%)  |  "
              f"Пики: {retro_highs}/{len(highs)}  |  Дно: {retro_lows}/{len(lows)}")
        print(f"    Baseline: {retro_base:.1f}%  |  Разница: {diff:+.1f}%  |  "
              f"p={p_binom:.4f}{sig}")

    # --- 4. ЗАТМЕНИЯ ---
    print("\n\n" + "-" * 70)
    print("4. ЗАТМЕНИЯ И РАЗВОРОТЫ")
    print("-" * 70)

    near_eclipse_pivots = pdf[pdf["near_eclipse"]]
    near_base = bdf["near_eclipse"].mean() * 100

    print(f"\n  Развороты в ±7 днях от затмения: {len(near_eclipse_pivots)}/{len(pdf)} "
          f"({len(near_eclipse_pivots)/len(pdf)*100:.1f}%)")
    print(f"  Baseline (обычные дни в ±7д от затмения): {near_base:.1f}%")

    if len(near_eclipse_pivots) > 0:
        p_ecl = stats.binomtest(len(near_eclipse_pivots), len(pdf), bdf["near_eclipse"].mean()).pvalue
        print(f"  p-value (биномиальный тест): {p_ecl:.4f}")

        print(f"\n  Конкретные развороты рядом с затмениями:")
        print(f"  {'Дата разворота':<16} {'Цена':>10} {'Тип':>15} {'До затмения':>12}")
        for _, row in near_eclipse_pivots.iterrows():
            print(f"  {row['date'].strftime('%Y-%m-%d'):<16} ${row['price']:>9,.0f} "
                  f"{row['pivot_type']:>15} {row['eclipse_days']:>8} дней")

    # --- 5. АСПЕКТЫ ---
    print("\n\n" + "-" * 70)
    print("5. ПЛАНЕТАРНЫЕ АСПЕКТЫ В МОМЕНТЫ РАЗВОРОТОВ")
    print("-" * 70)

    for aspect_col, aspect_name in [
        ("has_square", "Квадратура"),
        ("has_opposition", "Оппозиция"),
        ("has_conjunction", "Соединение"),
        ("has_trine", "Трин"),
    ]:
        asp_pivots = pdf[aspect_col].sum()
        asp_highs = highs[aspect_col].sum()
        asp_lows = lows[aspect_col].sum()
        asp_base = bdf[aspect_col].mean() * 100
        asp_pct = asp_pivots / len(pdf) * 100

        p_asp = stats.binomtest(int(asp_pivots), len(pdf), bdf[aspect_col].mean()).pvalue

        sig = " *" if p_asp < 0.05 else ""
        print(f"\n  {aspect_name}:")
        print(f"    При разворотах: {asp_pivots}/{len(pdf)} ({asp_pct:.1f}%)  |  "
              f"Пики: {asp_highs}/{len(highs)}  |  Дно: {asp_lows}/{len(lows)}")
        print(f"    Baseline: {asp_base:.1f}%  |  Разница: {asp_pct - asp_base:+.1f}%  |  "
              f"p={p_asp:.4f}{sig}")

    # --- 6. КОНКРЕТНЫЕ АСПЕКТЫ (частота) ---
    print("\n\n" + "-" * 70)
    print("6. САМЫЕ ЧАСТЫЕ АСПЕКТЫ ПРИ РАЗВОРОТАХ")
    print("-" * 70)

    all_aspects_pivot = []
    for aspects in pdf["aspects"]:
        all_aspects_pivot.extend(aspects)
    aspect_freq = Counter(all_aspects_pivot)

    all_aspects_base = []
    for aspects in bdf["aspects"]:
        all_aspects_base.extend(aspects)
    base_freq = Counter(all_aspects_base)

    print(f"\n  {'Аспект':<35} {'При разворотах':>15} {'Baseline%':>10} {'Diff':>8}")
    for asp, cnt in aspect_freq.most_common(20):
        asp_pct = cnt / len(pdf) * 100
        base_pct = base_freq[asp] / len(bdf) * 100
        diff = asp_pct - base_pct
        marker = " <<<" if abs(diff) > 10 else ""
        print(f"  {asp:<35} {cnt:>5} ({asp_pct:>5.1f}%) {base_pct:>8.1f}%  {diff:>+6.1f}%{marker}")

    # --- 7. ЗНАК СОЛНЦА (сезон) ---
    print("\n\n" + "-" * 70)
    print("7. ЗНАК СОЛНЦА (СЕЗОН) ПРИ РАЗВОРОТАХ")
    print("-" * 70)

    sun_pivots = Counter(pdf["sun_sign"])
    sun_base = Counter(bdf["sun_sign"])
    chi2_sun, p_sun = chi_square_test(sun_pivots, sun_base, ZODIAC_SIGNS)

    print(f"\n{'Знак (месяц)':<16} {'Развороты':>10} {'Пики':>6} {'Дно':>6} {'Base%':>7} {'Diff':>7}")
    sun_highs = Counter(highs["sun_sign"])
    sun_lows = Counter(lows["sun_sign"])
    for sign in ZODIAC_SIGNS:
        cnt = sun_pivots[sign]
        pct = cnt / len(pdf) * 100
        base_pct = sun_base[sign] / len(bdf) * 100
        diff = pct - base_pct
        marker = " <<<" if abs(diff) > 3 else ""
        print(f"{sign:<16} {cnt:>4} ({pct:>4.1f}%) {sun_highs[sign]:>4}   {sun_lows[sign]:>4}   "
              f"{base_pct:>5.1f}%  {diff:>+5.1f}%{marker}")

    print(f"\n  Хи-квадрат: χ²={chi2_sun}, p={p_sun}")

    # --- 8. MAJOR РАЗВОРОТЫ ДЕТАЛЬНО ---
    print("\n\n" + "-" * 70)
    print("8. АСТРО-ПРОФИЛЬ КАЖДОГО КРУПНОГО РАЗВОРОТА (major + global)")
    print("-" * 70)

    major_df = pdf[pdf["pivot_type"].str.contains("global|major")]
    print(f"\n{'Дата':<12} {'Цена':>10} {'Тип':<15} {'Луна фаза':<12} {'Луна знак':<12} "
          f"{'Hg retro':>9} {'Затм.':>6} {'Аспекты'}")
    for _, row in major_df.iterrows():
        hg = "ДА" if row["mercury_retro"] else "нет"
        ecl = f"{row['eclipse_days']}д" if row["eclipse_days"] <= 14 else "-"
        aspects_short = ", ".join(a.split(" ")[0] for a in row["aspects"][:4])
        if len(row["aspects"]) > 4:
            aspects_short += f" +{len(row['aspects'])-4}"
        print(f"{row['date'].strftime('%Y-%m-%d'):<12} ${row['price']:>9,.0f} {row['pivot_type']:<15} "
              f"{row['moon_quarter']:<12} {row['moon_sign']:<12} {hg:>9} {ecl:>6} {aspects_short}")

    # ============================================================
    # ВИЗУАЛИЗАЦИЯ
    # ============================================================
    fig, axes = plt.subplots(2, 3, figsize=(22, 13))

    # 1. Фазы Луны: развороты vs baseline
    ax = axes[0, 0]
    x = range(len(quarters))
    pivot_pcts = [pivot_q[q] / len(pdf) * 100 for q in quarters]
    base_pcts = [base_q[q] / len(bdf) * 100 for q in quarters]
    w = 0.35
    ax.bar([i - w/2 for i in x], pivot_pcts, w, label="Развороты", color="#FF6B6B", edgecolor="black", linewidth=0.5)
    ax.bar([i + w/2 for i in x], base_pcts, w, label="Baseline", color="#4ECDC4", edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(quarters)
    ax.set_ylabel("%")
    ax.set_title(f"Фазы Луны при разворотах\nχ²={chi2}, p={p_chi}", fontweight="bold")
    ax.legend()

    # 2. Знаки Луны
    ax = axes[0, 1]
    pivot_sign_pcts = [pivot_signs[s] / len(pdf) * 100 for s in ZODIAC_SIGNS]
    base_sign_pcts = [base_signs[s] / len(bdf) * 100 for s in ZODIAC_SIGNS]
    diffs = [p - b for p, b in zip(pivot_sign_pcts, base_sign_pcts)]
    colors = ["#4CAF50" if d >= 0 else "#F44336" for d in diffs]
    ax.barh(ZODIAC_SIGNS, diffs, color=colors, edgecolor="black", linewidth=0.5)
    ax.axvline(x=0, color="gray", linewidth=0.5)
    ax.set_xlabel("Разница от baseline (%)")
    ax.set_title(f"Знаки Луны: развороты vs baseline\nχ²={chi2_s}, p={p_chi_s}", fontweight="bold")

    # 3. Пики vs Дно по знакам
    ax = axes[0, 2]
    high_pcts = [high_signs[s] / len(highs) * 100 if len(highs) > 0 else 0 for s in ZODIAC_SIGNS]
    low_pcts = [low_signs[s] / len(lows) * 100 if len(lows) > 0 else 0 for s in ZODIAC_SIGNS]
    x = range(len(ZODIAC_SIGNS))
    ax.barh([i + 0.2 for i in x], high_pcts, 0.4, label="Пики", color="#FF6B6B", edgecolor="black", linewidth=0.3)
    ax.barh([i - 0.2 for i in x], low_pcts, 0.4, label="Дно", color="#4ECDC4", edgecolor="black", linewidth=0.3)
    ax.set_yticks(x)
    ax.set_yticklabels(ZODIAC_SIGNS)
    ax.set_xlabel("%")
    ax.set_title("Знаки Луны: Пики vs Дно", fontweight="bold")
    ax.legend()

    # 4. Ретроградные планеты
    ax = axes[1, 0]
    retro_data = {}
    for planet, col in [("Меркурий", "mercury_retro"), ("Венера", "venus_retro"), ("Марс", "mars_retro")]:
        retro_data[planet] = {
            "pivot": pdf[col].mean() * 100,
            "base": bdf[col].mean() * 100,
        }
    planets_list = list(retro_data.keys())
    x = range(len(planets_list))
    pivot_retro = [retro_data[p]["pivot"] for p in planets_list]
    base_retro = [retro_data[p]["base"] for p in planets_list]
    ax.bar([i - w/2 for i in x], pivot_retro, w, label="При разворотах", color="#FF6B6B", edgecolor="black", linewidth=0.5)
    ax.bar([i + w/2 for i in x], base_retro, w, label="Baseline", color="#4ECDC4", edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(planets_list)
    ax.set_ylabel("% дней в ретрограде")
    ax.set_title("Ретроградные планеты при разворотах", fontweight="bold")
    ax.legend()

    # 5. Расстояние до затмения
    ax = axes[1, 1]
    ax.hist(pdf["eclipse_days"], bins=30, color="#FF9800", edgecolor="black", linewidth=0.5, alpha=0.7, label="Развороты")
    ax.hist(bdf["eclipse_days"], bins=30, color="#2196F3", edgecolor="black", linewidth=0.5, alpha=0.4,
            weights=np.ones(len(bdf)) * len(pdf) / len(bdf), label="Baseline (масшт.)")
    ax.axvline(x=7, color="red", linestyle="--", label="±7 дней")
    ax.set_xlabel("Дней до ближайшего затмения")
    ax.set_ylabel("Количество разворотов")
    ax.set_title("Расстояние от разворотов до затмений", fontweight="bold")
    ax.legend()

    # 6. Знак Солнца (сезонность)
    ax = axes[1, 2]
    sun_diffs = [sun_pivots[s] / len(pdf) * 100 - sun_base[s] / len(bdf) * 100 for s in ZODIAC_SIGNS]
    colors = ["#4CAF50" if d >= 0 else "#F44336" for d in sun_diffs]
    ax.barh(ZODIAC_SIGNS, sun_diffs, color=colors, edgecolor="black", linewidth=0.5)
    ax.axvline(x=0, color="gray", linewidth=0.5)
    ax.set_xlabel("Разница от baseline (%)")
    ax.set_title(f"Знак Солнца (сезон): развороты vs baseline\nχ²={chi2_sun}, p={p_sun}", fontweight="bold")

    plt.suptitle("BTC Развороты x Астрология — Анализ конкретных точек (2020-2026)",
                 fontsize=16, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig("astro_pivots_results.png", dpi=150, bbox_inches="tight")
    print("\n\nГрафик сохранён: astro_pivots_results.png")
    plt.close()

    # Сохраняем в БД
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS btc_pivot_astro (
            date TEXT PRIMARY KEY,
            price REAL,
            pivot_type TEXT,
            pct_change REAL,
            moon_phase REAL,
            moon_quarter TEXT,
            moon_sign TEXT,
            mercury_retro INTEGER,
            venus_retro INTEGER,
            mars_retro INTEGER,
            sun_sign TEXT,
            near_eclipse INTEGER,
            eclipse_days INTEGER,
            n_aspects INTEGER,
            aspects TEXT
        )
    """)
    conn.execute("DELETE FROM btc_pivot_astro")
    for _, row in pdf.iterrows():
        conn.execute(
            "INSERT INTO btc_pivot_astro VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                row["date"].strftime("%Y-%m-%d"), row["price"], row["pivot_type"],
                row["pct_change"], row["moon_phase"], row["moon_quarter"], row["moon_sign"],
                int(row["mercury_retro"]), int(row["venus_retro"]), int(row["mars_retro"]),
                row["sun_sign"], int(row["near_eclipse"]), row["eclipse_days"],
                row["n_aspects"], "|".join(row["aspects"]),
            )
        )
    conn.commit()
    conn.close()
    print(f"Астро-профили разворотов сохранены в БД: btc_pivot_astro ({len(pdf)} строк)")


if __name__ == "__main__":
    main()
