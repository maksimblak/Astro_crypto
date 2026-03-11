import os
"""
BTC x Астрология: Расширенный анализ V2
Новые факторы: Лунные узлы (Раху/Кету), Void of Course Moon,
Ингрессии планет, Плутон, Уран, Нептун.
Глубокий комбинаторный поиск корреляций.
"""

import sqlite3
import ephem
import math
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy import stats
from collections import Counter
from itertools import combinations
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

# Элементы знаков
ELEMENT_MAP = {
    "Овен": "Огонь", "Телец": "Земля", "Близнецы": "Воздух", "Рак": "Вода",
    "Лев": "Огонь", "Дева": "Земля", "Весы": "Воздух", "Скорпион": "Вода",
    "Стрелец": "Огонь", "Козерог": "Земля", "Водолей": "Воздух", "Рыбы": "Вода",
}

# Модальности
MODALITY_MAP = {
    "Овен": "Кардинальный", "Телец": "Фиксированный", "Близнецы": "Мутабельный",
    "Рак": "Кардинальный", "Лев": "Фиксированный", "Дева": "Мутабельный",
    "Весы": "Кардинальный", "Скорпион": "Фиксированный", "Стрелец": "Мутабельный",
    "Козерог": "Кардинальный", "Водолей": "Фиксированный", "Рыбы": "Мутабельный",
}


def get_zodiac_sign(lon_deg):
    return ZODIAC_SIGNS[int(lon_deg / 30) % 12]


def _get_ecliptic_lon(body):
    """Эклиптическая долгота в градусах."""
    return float(ephem.Ecliptic(body).lon) * 180 / math.pi


def _is_retrograde(planet_class, d_now, d_prev):
    lon_now = _get_ecliptic_lon(planet_class(d_now))
    lon_prev = _get_ecliptic_lon(planet_class(d_prev))
    diff = lon_now - lon_prev
    if diff > 180:
        diff -= 360
    elif diff < -180:
        diff += 360
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
    """
    Средний лунный узел (Раху — восходящий).
    Кету = Раху + 180°.
    PyEphem не имеет встроенных лунных узлов, используем формулу.
    """
    # Средний восходящий узел Луны (приближённая формула)
    # Epoch: J2000.0 = 2000 Jan 1.5 TT
    jd = ephem.julian_date(d)
    T = (jd - 2451545.0) / 36525.0  # столетия от J2000

    # Средняя долгота восходящего узла (градусы)
    omega = 125.04452 - 1934.136261 * T + 0.0020708 * T**2 + T**3 / 450000
    omega = omega % 360
    if omega < 0:
        omega += 360

    return omega  # Раху в градусах


def _is_void_of_course(d):
    """
    Void of Course Moon: Луна не формирует точных аспектов
    до выхода из текущего знака.
    Упрощение: проверяем аспекты Луны с планетами в пределах
    остатка знака (до следующих 30° границы).
    """
    moon = ephem.Moon(d)
    moon_lon = _get_ecliptic_lon(moon)
    # Градусы до конца текущего знака
    degrees_left = 30 - (moon_lon % 30)

    # Скорость Луны ~13°/день, проверяем планеты в этом диапазоне
    planet_classes = [ephem.Sun, ephem.Mercury, ephem.Venus, ephem.Mars,
                      ephem.Jupiter, ephem.Saturn]

    aspect_angles = [0, 60, 90, 120, 180]
    orb = 3  # узкий орб для VoC

    for step in range(int(degrees_left)):
        # Проверяем каждый градус пути Луны до конца знака
        check_d = ephem.Date(d + step / 13.0)  # ~1 градус = 1/13 дня
        check_moon = ephem.Moon(check_d)
        check_moon_lon = _get_ecliptic_lon(check_moon)

        for pc in planet_classes:
            planet_lon = _get_ecliptic_lon(pc(check_d))
            diff = abs(check_moon_lon - planet_lon)
            if diff > 180:
                diff = 360 - diff
            for angle in aspect_angles:
                if abs(diff - angle) <= orb:
                    return False  # Есть аспект — не VoC

    return True  # Нет аспектов до конца знака


def _detect_ingress(planet_class, d, window_hours=12):
    """
    Планета сменила знак в пределах ±window часов.
    Возвращает (bool, new_sign или None).
    """
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


def get_extended_astro(date):
    """Максимально полный астро-профиль."""
    d = ephem.Date(date)
    d_prev = ephem.Date(date - timedelta(days=1))
    moon = ephem.Moon(d)

    # === Фаза Луны ===
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

    lunar_day = int(position * 29.5) + 1

    # === Позиции планет ===
    moon_lon = _get_ecliptic_lon(moon)
    moon_sign = get_zodiac_sign(moon_lon)

    planet_data = {}
    planet_classes = {
        "Солнце": ephem.Sun, "Меркурий": ephem.Mercury, "Венера": ephem.Venus,
        "Марс": ephem.Mars, "Юпитер": ephem.Jupiter, "Сатурн": ephem.Saturn,
    }

    bodies = {"Луна": moon_lon}
    for name, cls in planet_classes.items():
        body = cls(d)
        lon = _get_ecliptic_lon(body)
        bodies[name] = lon
        sign = get_zodiac_sign(lon)
        planet_data[name] = {"lon": lon, "sign": sign}

    sun_sign = planet_data["Солнце"]["sign"]
    jupiter_sign = planet_data["Юпитер"]["sign"]
    saturn_sign = planet_data["Сатурн"]["sign"]
    mars_sign = planet_data["Марс"]["sign"]
    venus_sign = planet_data["Венера"]["sign"]

    # === Лунные узлы ===
    rahu_lon = _get_lunar_node(d)
    rahu_sign = get_zodiac_sign(rahu_lon)
    ketu_lon = (rahu_lon + 180) % 360
    ketu_sign = get_zodiac_sign(ketu_lon)

    # Луна рядом с узлом? (±10°)
    moon_rahu_dist = abs(moon_lon - rahu_lon)
    if moon_rahu_dist > 180:
        moon_rahu_dist = 360 - moon_rahu_dist
    moon_ketu_dist = abs(moon_lon - ketu_lon)
    if moon_ketu_dist > 180:
        moon_ketu_dist = 360 - moon_ketu_dist
    near_node = moon_rahu_dist <= 10 or moon_ketu_dist <= 10
    near_rahu = moon_rahu_dist <= 10
    near_ketu = moon_ketu_dist <= 10

    # === Ретроградность ===
    retros = {}
    for name, cls in planet_classes.items():
        if name == "Солнце":
            continue
        retros[name] = _is_retrograde(cls, d, d_prev)

    retro_count = sum(retros.values())

    # === Стационарность ===
    stations = {}
    for name, cls in planet_classes.items():
        if name == "Солнце":
            continue
        stations[name] = _is_stationary(cls, d)
    any_station = any(stations.values())

    # === Void of Course Moon ===
    voc = _is_void_of_course(d)

    # === Ингрессии ===
    ingresses = {}
    for name, cls in planet_classes.items():
        is_ingress, new_sign = _detect_ingress(cls, d, window_hours=12)
        ingresses[name] = is_ingress
    moon_ingress, _ = _detect_ingress(ephem.Moon, d, window_hours=6)
    ingresses["Луна"] = moon_ingress
    any_ingress = any(ingresses.values())

    # === Аспекты ===
    aspect_defs = {
        "conj": (0, 8), "sext": (60, 6), "sq": (90, 8),
        "tri": (120, 8), "opp": (180, 8),
    }
    aspects = []
    body_names = list(bodies.keys())
    for i in range(len(body_names)):
        for j in range(i + 1, len(body_names)):
            b1, b2 = body_names[i], body_names[j]
            d_angle = abs(bodies[b1] - bodies[b2])
            if d_angle > 180:
                d_angle = 360 - d_angle
            for asp_name, (angle, orb) in aspect_defs.items():
                if abs(d_angle - angle) <= orb:
                    aspects.append(f"{b1}-{b2}:{asp_name}")

    # Аспекты к лунным узлам
    for body_name, body_lon in bodies.items():
        for node_name, node_lon in [("Раху", rahu_lon), ("Кету", ketu_lon)]:
            d_angle = abs(body_lon - node_lon)
            if d_angle > 180:
                d_angle = 360 - d_angle
            if d_angle <= 8:  # conjunction
                aspects.append(f"{body_name}-{node_name}:conj")
            elif abs(d_angle - 90) <= 8:  # square
                aspects.append(f"{body_name}-{node_name}:sq")

    tension_count = sum(1 for a in aspects if ":sq" in a or ":opp" in a)
    harmony_count = sum(1 for a in aspects if ":tri" in a or ":sext" in a)

    # === Затмения ===
    min_eclipse_days = min(abs((date - ed).days) for ed in ECLIPSE_DATES)

    # === Элементы и модальности ===
    moon_element = ELEMENT_MAP[moon_sign]
    moon_modality = MODALITY_MAP[moon_sign]
    sun_element = ELEMENT_MAP[sun_sign]

    return {
        # Луна
        "moon_phase": round(phase, 3),
        "moon_quarter": quarter,
        "lunar_day": lunar_day,
        "moon_sign": moon_sign,
        "moon_element": moon_element,
        "moon_modality": moon_modality,
        "voc": voc,
        "moon_ingress": moon_ingress,
        # Узлы
        "rahu_sign": rahu_sign,
        "ketu_sign": ketu_sign,
        "near_node": near_node,
        "near_rahu": near_rahu,
        "near_ketu": near_ketu,
        "moon_rahu_dist": round(moon_rahu_dist, 1),
        # Планеты
        "sun_sign": sun_sign,
        "sun_element": sun_element,
        "jupiter_sign": jupiter_sign,
        "saturn_sign": saturn_sign,
        "mars_sign": mars_sign,
        "venus_sign": venus_sign,
        # Ретро
        "mercury_retro": retros.get("Меркурий", False),
        "venus_retro": retros.get("Венера", False),
        "mars_retro": retros.get("Марс", False),
        "jupiter_retro": retros.get("Юпитер", False),
        "saturn_retro": retros.get("Сатурн", False),
        "retro_count": retro_count,
        # Стационарность
        "any_station": any_station,
        "stations": stations,
        # Ингрессии
        "any_ingress": any_ingress,
        "moon_ingress_flag": moon_ingress,
        "ingresses": ingresses,
        # Аспекты
        "aspects": aspects,
        "n_aspects": len(aspects),
        "tension_count": tension_count,
        "harmony_count": harmony_count,
        "tension_ratio": round(tension_count / max(len(aspects), 1), 3),
        # Затмения
        "eclipse_days": min_eclipse_days,
        "near_eclipse": min_eclipse_days <= 7,
    }


# ============================================================
# ЗАГРУЗКА ДАННЫХ
# ============================================================

def load_data():
    conn = sqlite3.connect(DB_PATH)
    pivots = pd.read_sql("""
        SELECT date, price, type, pct_change FROM btc_pivots
        WHERE date >= '2020-01-01' ORDER BY date
    """, conn)
    all_days = pd.read_sql("""
        SELECT date, close FROM btc_daily
        WHERE date >= '2020-01-01' ORDER BY date
    """, conn)
    conn.close()
    pivots["date"] = pd.to_datetime(pivots["date"])
    all_days["date"] = pd.to_datetime(all_days["date"])
    return pivots, all_days


def compute_datasets(pivots, all_days):
    print("Астро для разворотов...")
    pivot_records = []
    for idx, row in pivots.iterrows():
        astro = get_extended_astro(row["date"].to_pydatetime())
        astro["date"] = row["date"]
        astro["price"] = row["price"]
        astro["pivot_type"] = row["type"]
        astro["pct_change"] = row["pct_change"]
        astro["is_high"] = "high" in row["type"]
        astro["is_major"] = "major" in row["type"] or "global" in row["type"]
        pivot_records.append(astro)
        if (idx + 1) % 20 == 0:
            print(f"  {idx + 1}/{len(pivots)} разворотов...")

    print("Астро для baseline (каждый 3-й день)...")
    base_records = []
    sampled = all_days.iloc[::3]
    for idx, (_, row) in enumerate(sampled.iterrows()):
        astro = get_extended_astro(row["date"].to_pydatetime())
        base_records.append(astro)
        if (idx + 1) % 100 == 0:
            print(f"  {idx + 1}/{len(sampled)} baseline дней...")

    return pd.DataFrame(pivot_records), pd.DataFrame(base_records)


# ============================================================
# АНАЛИЗ 1: ЛУННЫЕ УЗЛЫ (РАХУ / КЕТУ)
# ============================================================

def analyze_lunar_nodes(pdf, bdf):
    print("\n" + "=" * 90)
    print("1. ЛУННЫЕ УЗЛЫ (РАХУ / КЕТУ)")
    print("=" * 90)

    # Луна рядом с узлом при разворотах
    node_pivot = pdf["near_node"].sum()
    node_base = bdf["near_node"].mean()
    node_pct = node_pivot / len(pdf) * 100
    node_base_pct = node_base * 100

    p_val = stats.binomtest(int(node_pivot), len(pdf), max(node_base, 0.001)).pvalue
    sig = " *" if p_val < 0.05 else ""

    print(f"\n  Луна ±10° от лунного узла:")
    print(f"    При разворотах: {node_pivot}/{len(pdf)} ({node_pct:.1f}%)")
    print(f"    Baseline: {node_base_pct:.1f}%")
    print(f"    p-value: {p_val:.4f}{sig}")

    # Раху vs Кету отдельно
    for name, col in [("Раху (восх.)", "near_rahu"), ("Кету (нисх.)", "near_ketu")]:
        cnt = pdf[col].sum()
        b = bdf[col].mean()
        if cnt > 0:
            p = stats.binomtest(int(cnt), len(pdf), max(b, 0.001)).pvalue
            print(f"\n  Луна ±10° от {name}:")
            print(f"    При разворотах: {cnt}/{len(pdf)} ({cnt/len(pdf)*100:.1f}%)")
            print(f"    Baseline: {b*100:.1f}%  p={p:.4f}")

            # Пики vs Дно
            highs = pdf[pdf["is_high"]]
            lows = pdf[~pdf["is_high"]]
            h_cnt = highs[col].sum()
            l_cnt = lows[col].sum()
            print(f"    При пиках: {h_cnt}/{len(highs)}, при дно: {l_cnt}/{len(lows)}")

    # Знак Раху при разворотах
    print(f"\n  --- Знак Раху при разворотах ---")
    rahu_pivots = Counter(pdf["rahu_sign"])
    rahu_base = Counter(bdf["rahu_sign"])
    for sign in sorted(rahu_pivots.keys()):
        p_pct = rahu_pivots[sign] / len(pdf) * 100
        b_pct = rahu_base.get(sign, 0) / len(bdf) * 100
        if p_pct > 0 or b_pct > 0:
            print(f"    {sign:<12} развороты: {rahu_pivots[sign]:>3} ({p_pct:.1f}%)  base: {b_pct:.1f}%")


# ============================================================
# АНАЛИЗ 2: VOID OF COURSE MOON
# ============================================================

def analyze_voc(pdf, bdf):
    print("\n\n" + "=" * 90)
    print("2. VOID OF COURSE MOON")
    print("=" * 90)

    voc_pivot = pdf["voc"].sum()
    voc_base = bdf["voc"].mean()
    voc_pct = voc_pivot / len(pdf) * 100
    voc_base_pct = voc_base * 100

    p_val = stats.binomtest(int(voc_pivot), len(pdf), max(voc_base, 0.001)).pvalue
    sig = " *" if p_val < 0.05 else ""

    print(f"\n  Void of Course Moon при разворотах:")
    print(f"    При разворотах: {voc_pivot}/{len(pdf)} ({voc_pct:.1f}%)")
    print(f"    Baseline: {voc_base_pct:.1f}%")
    print(f"    p-value: {p_val:.4f}{sig}")

    # VoC при пиках vs дно
    highs = pdf[pdf["is_high"]]
    lows = pdf[~pdf["is_high"]]
    h_voc = highs["voc"].sum()
    l_voc = lows["voc"].sum()
    print(f"\n    При пиках: {h_voc}/{len(highs)} ({h_voc/max(len(highs),1)*100:.1f}%)")
    print(f"    При дно:   {l_voc}/{len(lows)} ({l_voc/max(len(lows),1)*100:.1f}%)")

    if voc_pivot > 0:
        print(f"\n  Развороты с VoC:")
        for _, row in pdf[pdf["voc"]].iterrows():
            print(f"    {row['date'].strftime('%Y-%m-%d')} ${row['price']:>9,.0f} {row['pivot_type']:<15} "
                  f"{row['moon_quarter']} Луна-{row['moon_sign']}")


# ============================================================
# АНАЛИЗ 3: ИНГРЕССИИ ПЛАНЕТ
# ============================================================

def analyze_ingresses(pdf, bdf):
    print("\n\n" + "=" * 90)
    print("3. ИНГРЕССИИ (СМЕНА ЗНАКА ПЛАНЕТОЙ)")
    print("=" * 90)

    # Любая ингрессия
    ingress_pivot = pdf["any_ingress"].sum()
    ingress_base = bdf["any_ingress"].mean()
    p_val = stats.binomtest(int(ingress_pivot), len(pdf), max(ingress_base, 0.001)).pvalue
    sig = " *" if p_val < 0.05 else ""

    print(f"\n  Любая планета меняет знак (±12ч):")
    print(f"    При разворотах: {ingress_pivot}/{len(pdf)} ({ingress_pivot/len(pdf)*100:.1f}%)")
    print(f"    Baseline: {ingress_base*100:.1f}%")
    print(f"    p-value: {p_val:.4f}{sig}")

    # Ингрессия Луны
    moon_ing_pivot = pdf["moon_ingress_flag"].sum()
    moon_ing_base = bdf["moon_ingress_flag"].mean()
    if moon_ing_pivot > 0:
        p_moon = stats.binomtest(int(moon_ing_pivot), len(pdf), max(moon_ing_base, 0.001)).pvalue
        print(f"\n  Луна меняет знак (±6ч):")
        print(f"    При разворотах: {moon_ing_pivot}/{len(pdf)} ({moon_ing_pivot/len(pdf)*100:.1f}%)")
        print(f"    Baseline: {moon_ing_base*100:.1f}%  p={p_moon:.4f}")

    # По планетам
    planets = ["Солнце", "Меркурий", "Венера", "Марс", "Юпитер", "Сатурн"]
    print(f"\n  --- По планетам ---")

    for planet in planets:
        # Достаём из словаря ingresses
        p_cnt = sum(1 for _, row in pdf.iterrows() if row["ingresses"].get(planet, False))
        b_cnt = sum(1 for _, row in bdf.iterrows() if row["ingresses"].get(planet, False))
        b_rate = b_cnt / len(bdf) if len(bdf) > 0 else 0

        if p_cnt > 0:
            p_v = stats.binomtest(p_cnt, len(pdf), max(b_rate, 0.001)).pvalue
            sig = " *" if p_v < 0.05 else ""
            print(f"    {planet:<12} при разворотах: {p_cnt}/{len(pdf)} "
                  f"({p_cnt/len(pdf)*100:.1f}%)  base: {b_rate*100:.1f}%  p={p_v:.4f}{sig}")


# ============================================================
# АНАЛИЗ 4: ЭЛЕМЕНТЫ И МОДАЛЬНОСТИ
# ============================================================

def analyze_elements(pdf, bdf):
    print("\n\n" + "=" * 90)
    print("4. ЭЛЕМЕНТЫ И МОДАЛЬНОСТИ ЛУНЫ")
    print("=" * 90)

    highs = pdf[pdf["is_high"]]
    lows = pdf[~pdf["is_high"]]

    for cat_name, col in [("Элемент Луны", "moon_element"), ("Модальность Луны", "moon_modality")]:
        categories = sorted(pdf[col].unique())
        print(f"\n  --- {cat_name} ---")
        print(f"  {'Значение':<16} {'Все разв.':>10} {'Пики':>8} {'Дно':>8} {'Base':>8} {'p-value':>10}")

        p_counts = Counter(pdf[col])
        h_counts = Counter(highs[col])
        l_counts = Counter(lows[col])
        b_counts = Counter(bdf[col])

        for cat in categories:
            p_pct = p_counts.get(cat, 0) / len(pdf) * 100
            h_pct = h_counts.get(cat, 0) / max(len(highs), 1) * 100
            l_pct = l_counts.get(cat, 0) / max(len(lows), 1) * 100
            b_pct = b_counts.get(cat, 0) / len(bdf) * 100

            b_rate = b_counts.get(cat, 0) / len(bdf)
            if p_counts.get(cat, 0) > 0 and b_rate > 0:
                p_val = stats.binomtest(p_counts[cat], len(pdf), b_rate).pvalue
            else:
                p_val = 1.0
            sig = " *" if p_val < 0.05 else ""

            print(f"  {cat:<16} {p_counts.get(cat,0):>4} ({p_pct:>4.1f}%) "
                  f"{h_counts.get(cat,0):>3} ({h_pct:>4.1f}%) "
                  f"{l_counts.get(cat,0):>3} ({l_pct:>4.1f}%) "
                  f"{b_pct:>6.1f}% {p_val:>10.4f}{sig}")


# ============================================================
# АНАЛИЗ 5: РАСШИРЕННЫЙ КОМБИНАТОРНЫЙ ПОИСК
# ============================================================

def analyze_extended_combos(pdf, bdf):
    print("\n\n" + "=" * 90)
    print("5. РАСШИРЕННЫЙ КОМБИНАТОРНЫЙ ПОИСК")
    print("=" * 90)

    def make_features(df):
        f = pd.DataFrame()
        f["новолуние"] = df["moon_quarter"] == "Новолуние"
        f["полнолуние"] = df["moon_quarter"] == "Полнолуние"
        f["растущая"] = df["moon_quarter"] == "Растущая"
        f["убывающая"] = df["moon_quarter"] == "Убывающая"
        f["hg_retro"] = df["mercury_retro"]
        f["venus_retro"] = df["venus_retro"]
        f["mars_retro"] = df["mars_retro"]
        f["jupiter_retro"] = df["jupiter_retro"]
        f["saturn_retro"] = df["saturn_retro"]
        f["station"] = df["any_station"]
        f["eclipse_7d"] = df["near_eclipse"]
        f["hi_tension"] = df["tension_count"] >= 3
        f["hi_harmony"] = df["harmony_count"] >= 3
        f["many_retro"] = df["retro_count"] >= 2
        f["voc"] = df["voc"]
        f["near_node"] = df["near_node"]
        f["near_rahu"] = df["near_rahu"]
        f["near_ketu"] = df["near_ketu"]
        f["ingress"] = df["any_ingress"]
        f["moon_ingress"] = df["moon_ingress_flag"]

        # Элементы Луны
        for el in ["Огонь", "Земля", "Воздух", "Вода"]:
            f[f"луна_{el}"] = df["moon_element"] == el

        # Модальности Луны
        for mod in ["Кардинальный", "Фиксированный", "Мутабельный"]:
            f[f"луна_{mod}"] = df["moon_modality"] == mod

        # Знаки Луны (топ)
        for sign in ZODIAC_SIGNS:
            f[f"луна_{sign}"] = df["moon_sign"] == sign

        return f

    pf = make_features(pdf)
    bf = make_features(bdf)

    # Все пары (без знаков Луны — их слишком много)
    core_features = [c for c in pf.columns if not c.startswith("луна_")]
    results = []

    # Пары core факторов
    for f1, f2 in combinations(core_features, 2):
        p_both = (pf[f1] & pf[f2]).sum()
        b_both = (bf[f1] & bf[f2]).mean()

        if p_both < 3 or b_both < 0.005:
            continue

        p_pct = p_both / len(pf) * 100
        b_pct = b_both * 100
        ratio = p_pct / max(b_pct, 0.1)

        if ratio > 1.5 or ratio < 0.5:
            p_val = stats.binomtest(int(p_both), len(pf), b_both).pvalue
            results.append({
                "combo": f"{f1} + {f2}",
                "pivots": int(p_both),
                "pivot_pct": round(p_pct, 1),
                "base_pct": round(b_pct, 1),
                "ratio": round(ratio, 2),
                "p_value": round(p_val, 4),
            })

    # Фаза + Элемент Луны
    for quarter in ["новолуние", "полнолуние", "растущая", "убывающая"]:
        for el in ["Огонь", "Земля", "Воздух", "Вода"]:
            el_col = f"луна_{el}"
            p_both = (pf[quarter] & pf[el_col]).sum()
            b_both = (bf[quarter] & bf[el_col]).mean()

            if p_both < 2 or b_both < 0.005:
                continue
            p_pct = p_both / len(pf) * 100
            b_pct = b_both * 100
            ratio = p_pct / max(b_pct, 0.1)

            if ratio > 1.5:
                p_val = stats.binomtest(int(p_both), len(pf), b_both).pvalue
                results.append({
                    "combo": f"{quarter} + Луна-{el}",
                    "pivots": int(p_both),
                    "pivot_pct": round(p_pct, 1),
                    "base_pct": round(b_pct, 1),
                    "ratio": round(ratio, 2),
                    "p_value": round(p_val, 4),
                })

    # Тройки (только самые значимые core факторы)
    sig_core = [c for c in core_features if pf[c].sum() >= 5]
    for f1, f2, f3 in combinations(sig_core, 3):
        p_both = (pf[f1] & pf[f2] & pf[f3]).sum()
        b_both = (bf[f1] & bf[f2] & bf[f3]).mean()

        if p_both < 3 or b_both < 0.003:
            continue

        p_pct = p_both / len(pf) * 100
        b_pct = b_both * 100
        ratio = p_pct / max(b_pct, 0.1)

        if ratio > 2.0:
            p_val = stats.binomtest(int(p_both), len(pf), b_both).pvalue
            results.append({
                "combo": f"{f1} + {f2} + {f3}",
                "pivots": int(p_both),
                "pivot_pct": round(p_pct, 1),
                "base_pct": round(b_pct, 1),
                "ratio": round(ratio, 2),
                "p_value": round(p_val, 4),
            })

    results.sort(key=lambda x: x["p_value"])

    print(f"\n  Найдено {len(results)} значимых комбинаций")
    print(f"  {'Комбинация':<50} {'N':>4} {'Разв%':>7} {'Base%':>7} {'Ratio':>7} {'p-value':>10}")
    print("  " + "-" * 90)
    for r in results[:30]:
        sig = " **" if r["p_value"] < 0.01 else " *" if r["p_value"] < 0.05 else ""
        print(f"  {r['combo']:<50} {r['pivots']:>4} {r['pivot_pct']:>5.1f}% "
              f"{r['base_pct']:>5.1f}% {r['ratio']:>6.2f}x {r['p_value']:>10.4f}{sig}")

    return results


# ============================================================
# АНАЛИЗ 6: ПИКИ vs ДНО с НОВЫМИ ФАКТОРАМИ
# ============================================================

def analyze_highs_vs_lows_extended(pdf):
    print("\n\n" + "=" * 90)
    print("6. ПИКИ vs ДНО — РАСШИРЕННЫЕ ПАТТЕРНЫ")
    print("=" * 90)

    highs = pdf[pdf["is_high"]]
    lows = pdf[~pdf["is_high"]]

    # Бинарные факторы
    binary_factors = [
        ("voc", "Void of Course"),
        ("near_node", "Луна у узла (±10°)"),
        ("near_rahu", "Луна у Раху"),
        ("near_ketu", "Луна у Кету"),
        ("any_ingress", "Любая ингрессия"),
        ("moon_ingress_flag", "Ингрессия Луны"),
        ("any_station", "Стационарная планета"),
        ("mercury_retro", "Меркурий ретро"),
        ("near_eclipse", "Затмение ±7д"),
    ]

    print(f"\n  {'Фактор':<30} {'Пики':>10} {'Дно':>10} {'Разница':>10} {'p(Fisher)':>10}")
    print("  " + "-" * 75)

    for col, name in binary_factors:
        h_cnt = highs[col].sum()
        l_cnt = lows[col].sum()
        h_pct = h_cnt / max(len(highs), 1) * 100
        l_pct = l_cnt / max(len(lows), 1) * 100
        diff = h_pct - l_pct

        # Fisher's exact test (2x2 table)
        table = [
            [h_cnt, len(highs) - h_cnt],
            [l_cnt, len(lows) - l_cnt],
        ]
        _, p_fisher = stats.fisher_exact(table)
        sig = " *" if p_fisher < 0.05 else ""

        direction = "→ПИКИ" if diff > 5 else "→ДНО" if diff < -5 else ""
        print(f"  {name:<30} {h_cnt:>3} ({h_pct:>4.1f}%) {l_cnt:>3} ({l_pct:>4.1f}%) "
              f"{diff:>+8.1f}% {p_fisher:>10.4f}{sig} {direction}")

    # Элементы
    print(f"\n  --- Элемент Луны: пики vs дно ---")
    for el in ["Огонь", "Земля", "Воздух", "Вода"]:
        h = (highs["moon_element"] == el).sum()
        l = (lows["moon_element"] == el).sum()
        h_pct = h / max(len(highs), 1) * 100
        l_pct = l / max(len(lows), 1) * 100
        diff = h_pct - l_pct
        direction = "→ПИКИ" if diff > 5 else "→ДНО" if diff < -5 else ""
        print(f"    {el:<12} пики: {h} ({h_pct:.1f}%)  дно: {l} ({l_pct:.1f}%)  {diff:+.1f}% {direction}")

    # Модальности
    print(f"\n  --- Модальность Луны: пики vs дно ---")
    for mod in ["Кардинальный", "Фиксированный", "Мутабельный"]:
        h = (highs["moon_modality"] == mod).sum()
        l = (lows["moon_modality"] == mod).sum()
        h_pct = h / max(len(highs), 1) * 100
        l_pct = l / max(len(lows), 1) * 100
        diff = h_pct - l_pct
        direction = "→ПИКИ" if diff > 5 else "→ДНО" if diff < -5 else ""
        print(f"    {mod:<16} пики: {h} ({h_pct:.1f}%)  дно: {l} ({l_pct:.1f}%)  {diff:+.1f}% {direction}")


# ============================================================
# АНАЛИЗ 7: АСПЕКТЫ К ЛУННЫМ УЗЛАМ
# ============================================================

def analyze_node_aspects(pdf, bdf):
    print("\n\n" + "=" * 90)
    print("7. АСПЕКТЫ К ЛУННЫМ УЗЛАМ ПРИ РАЗВОРОТАХ")
    print("=" * 90)

    # Собираем аспекты к Раху/Кету
    node_aspects_pivot = Counter()
    for aspects in pdf["aspects"]:
        for a in aspects:
            if "Раху" in a or "Кету" in a:
                node_aspects_pivot[a] += 1

    node_aspects_base = Counter()
    for aspects in bdf["aspects"]:
        for a in aspects:
            if "Раху" in a or "Кету" in a:
                node_aspects_base[a] += 1

    if node_aspects_pivot:
        print(f"\n  {'Аспект':<35} {'Развороты':>10} {'Base%':>8} {'Ratio':>8}")
        for asp, cnt in node_aspects_pivot.most_common(15):
            p_pct = cnt / len(pdf) * 100
            b_pct = node_aspects_base.get(asp, 0) / len(bdf) * 100
            ratio = p_pct / max(b_pct, 0.1)
            marker = " <<<" if ratio > 1.5 else ""
            print(f"  {asp:<35} {cnt:>4} ({p_pct:>5.1f}%) {b_pct:>6.1f}% {ratio:>7.2f}x{marker}")
    else:
        print("  Аспекты к узлам не найдены.")


# ============================================================
# АНАЛИЗ 8: ВРЕМЕННЫЕ ПАТТЕРНЫ + АСТРО
# ============================================================

def analyze_timing_patterns(pdf):
    print("\n\n" + "=" * 90)
    print("8. ВРЕМЕННЫЕ ПАТТЕРНЫ + АСТРО")
    print("=" * 90)

    pdf_sorted = pdf.sort_values("date")

    # Интервалы между разворотами
    intervals = []
    for i in range(1, len(pdf_sorted)):
        days = (pdf_sorted.iloc[i]["date"] - pdf_sorted.iloc[i-1]["date"]).days
        intervals.append(days)

    if intervals:
        print(f"\n  Интервалы между разворотами:")
        print(f"    Среднее: {np.mean(intervals):.1f} дней")
        print(f"    Медиана: {np.median(intervals):.1f} дней")
        print(f"    Мин: {min(intervals)}, Макс: {max(intervals)}")

        # Корреляция с лунным циклом (~29.5 дней)
        lunar_cycle = 29.53
        remainder = [i % lunar_cycle for i in intervals]
        print(f"\n  Остатки интервалов по модулю лунного цикла (29.5д):")
        print(f"    Среднее: {np.mean(remainder):.1f}")
        print(f"    Медиана: {np.median(remainder):.1f}")

        # Тест на равномерность (если развороты привязаны к лунному циклу,
        # остатки будут кластеризоваться)
        _, p_uniform = stats.kstest(remainder, stats.uniform(0, lunar_cycle).cdf)
        print(f"    KS-тест на равномерность: p={p_uniform:.4f}")
        if p_uniform < 0.05:
            print(f"    → Интервалы НЕ равномерны по лунному циклу (есть паттерн)")
        else:
            print(f"    → Интервалы равномерны (нет привязки к лунному циклу)")

    # День недели разворотов
    pdf_sorted["weekday"] = pdf_sorted["date"].dt.day_name()
    wd_counts = Counter(pdf_sorted["weekday"])
    print(f"\n  Дни недели разворотов:")
    for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
        cnt = wd_counts.get(day, 0)
        bar = "█" * cnt
        print(f"    {day:<12} {cnt:>3} {bar}")


# ============================================================
# ВИЗУАЛИЗАЦИЯ
# ============================================================

def plot_extended_results(pdf, bdf, combo_results):
    fig, axes = plt.subplots(2, 4, figsize=(28, 14))

    highs = pdf[pdf["is_high"]]
    lows = pdf[~pdf["is_high"]]

    # 1. Элементы Луны: пики vs дно
    ax = axes[0, 0]
    elements = ["Огонь", "Земля", "Воздух", "Вода"]
    h_el = [((highs["moon_element"] == el).sum() / max(len(highs), 1) * 100) for el in elements]
    l_el = [((lows["moon_element"] == el).sum() / max(len(lows), 1) * 100) for el in elements]
    x = range(len(elements))
    w = 0.35
    ax.bar([i - w/2 for i in x], h_el, w, label="Пики", color="#FF6B6B", edgecolor="black", linewidth=0.5)
    ax.bar([i + w/2 for i in x], l_el, w, label="Дно", color="#4ECDC4", edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(elements)
    ax.set_ylabel("%")
    ax.set_title("Элементы Луны: пики vs дно", fontweight="bold")
    ax.legend()

    # 2. Модальности
    ax = axes[0, 1]
    mods = ["Кардинальный", "Фиксированный", "Мутабельный"]
    h_mod = [((highs["moon_modality"] == m).sum() / max(len(highs), 1) * 100) for m in mods]
    l_mod = [((lows["moon_modality"] == m).sum() / max(len(lows), 1) * 100) for m in mods]
    x = range(len(mods))
    ax.bar([i - w/2 for i in x], h_mod, w, label="Пики", color="#FF6B6B", edgecolor="black", linewidth=0.5)
    ax.bar([i + w/2 for i in x], l_mod, w, label="Дно", color="#4ECDC4", edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(mods, fontsize=8)
    ax.set_ylabel("%")
    ax.set_title("Модальности Луны: пики vs дно", fontweight="bold")
    ax.legend()

    # 3. Лунные узлы — расстояние Луны от Раху
    ax = axes[0, 2]
    ax.hist(pdf["moon_rahu_dist"], bins=20, color="#FF9800", edgecolor="black",
            linewidth=0.5, alpha=0.7, label="Развороты")
    ax.hist(bdf["moon_rahu_dist"], bins=20, color="#2196F3", edgecolor="black",
            linewidth=0.5, alpha=0.4,
            weights=np.ones(len(bdf)) * len(pdf) / len(bdf), label="Baseline (масшт.)")
    ax.axvline(x=10, color="red", linestyle="--", label="±10° (у узла)")
    ax.set_xlabel("Расстояние Луна — Раху (°)")
    ax.set_ylabel("Кол-во")
    ax.set_title("Луна и лунный узел Раху", fontweight="bold")
    ax.legend(fontsize=8)

    # 4. VoC + ингрессии
    ax = axes[0, 3]
    factors = ["VoC", "Ингрессия\n(любая)", "Ингрессия\nЛуны", "У узла\n(±10°)"]
    p_vals = [
        pdf["voc"].mean() * 100, pdf["any_ingress"].mean() * 100,
        pdf["moon_ingress_flag"].mean() * 100, pdf["near_node"].mean() * 100,
    ]
    b_vals = [
        bdf["voc"].mean() * 100, bdf["any_ingress"].mean() * 100,
        bdf["moon_ingress_flag"].mean() * 100, bdf["near_node"].mean() * 100,
    ]
    x = range(len(factors))
    ax.bar([i - w/2 for i in x], p_vals, w, label="Развороты", color="#FF6B6B", edgecolor="black", linewidth=0.5)
    ax.bar([i + w/2 for i in x], b_vals, w, label="Baseline", color="#4ECDC4", edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(factors, fontsize=8)
    ax.set_ylabel("%")
    ax.set_title("Новые факторы: развороты vs baseline", fontweight="bold")
    ax.legend()

    # 5. Топ комбинации
    ax = axes[1, 0]
    if combo_results:
        top = combo_results[:12]
        names = [r["combo"][:35] for r in top]
        ratios = [r["ratio"] for r in top]
        p_colors = ["#4CAF50" if r["p_value"] < 0.05 else "#FFC107" if r["p_value"] < 0.1 else "#F44336" for r in top]
        ax.barh(range(len(names)), ratios, color=p_colors, edgecolor="black", linewidth=0.5)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=7)
        ax.axvline(x=1.0, color="gray", linestyle="--", linewidth=0.5)
        ax.set_xlabel("Ratio (развороты / baseline)")
        ax.set_title("Топ-12 комбинаций факторов", fontweight="bold")

    # 6. Tension vs Harmony + node proximity
    ax = axes[1, 1]
    scatter = ax.scatter(pdf["tension_count"], pdf["harmony_count"],
                        c=pdf["moon_rahu_dist"], cmap="RdYlGn",
                        s=80, edgecolors="black", linewidths=0.3, alpha=0.8)
    plt.colorbar(scatter, ax=ax, label="Расст. до Раху (°)")
    ax.set_xlabel("Напряжённые аспекты")
    ax.set_ylabel("Гармоничные аспекты")
    ax.set_title("Tension vs Harmony (цвет = расст. до узла)", fontweight="bold")

    # 7. Бинарные факторы: пики vs дно
    ax = axes[1, 2]
    binary_factors = [
        ("voc", "VoC"), ("near_node", "У узла"), ("any_ingress", "Ингрессия"),
        ("any_station", "Станция"), ("mercury_retro", "Hg retro"), ("near_eclipse", "Затмение"),
    ]
    factor_names = [bf[1] for bf in binary_factors]
    h_pcts = [highs[bf[0]].mean() * 100 for bf in binary_factors]
    l_pcts = [lows[bf[0]].mean() * 100 for bf in binary_factors]
    diffs = [h - l for h, l in zip(h_pcts, l_pcts)]
    colors = ["#FF6B6B" if d > 0 else "#4ECDC4" for d in diffs]
    ax.barh(factor_names, diffs, color=colors, edgecolor="black", linewidth=0.5)
    ax.axvline(x=0, color="gray", linewidth=0.5)
    ax.set_xlabel("Разница (Пики% - Дно%)")
    ax.set_title("Бинарные факторы: перекос пики↔дно", fontweight="bold")

    # 8. Лунный день
    ax = axes[1, 3]
    days = range(1, 31)
    p_day = Counter(pdf["lunar_day"])
    b_day = Counter(bdf["lunar_day"])
    p_v = [p_day.get(d, 0) / len(pdf) * 100 for d in days]
    b_v = [b_day.get(d, 0) / len(bdf) * 100 for d in days]
    ax.bar(days, p_v, color="#FF6B6B", alpha=0.7, label="Развороты")
    ax.plot(days, b_v, "k--", linewidth=1, label="Baseline")
    ax.set_xlabel("Лунный день")
    ax.set_ylabel("%")
    ax.set_title("Лунные дни при разворотах", fontweight="bold")
    ax.legend()

    plt.suptitle("BTC x Астрология — Расширенный анализ V2 (2020-2026)",
                 fontsize=16, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig("astro_extended_results.png", dpi=150, bbox_inches="tight")
    print("\nГрафик: astro_extended_results.png")
    plt.close()


# ============================================================
# ИТОГОВЫЙ ВЕРДИКТ
# ============================================================

def print_verdict(pdf, bdf, combo_results):
    print("\n\n" + "=" * 90)
    print("ИТОГОВЫЕ НАХОДКИ V2 — ВСЕ ЗНАЧИМЫЕ КОРРЕЛЯЦИИ")
    print("=" * 90)

    findings = []

    # Бинарные факторы
    binary_tests = [
        ("near_node", "Луна у лунного узла (±10°)"),
        ("near_rahu", "Луна у Раху"),
        ("near_ketu", "Луна у Кету"),
        ("voc", "Void of Course Moon"),
        ("any_ingress", "Любая ингрессия"),
        ("moon_ingress_flag", "Ингрессия Луны"),
        ("any_station", "Стационарная планета"),
        ("near_eclipse", "Затмение ±7д"),
        ("mercury_retro", "Меркурий ретро"),
        ("venus_retro", "Венера ретро"),
        ("mars_retro", "Марс ретро"),
        ("jupiter_retro", "Юпитер ретро"),
        ("saturn_retro", "Сатурн ретро"),
    ]

    for col, name in binary_tests:
        p_cnt = int(pdf[col].sum())
        b_rate = bdf[col].mean()
        if p_cnt > 0 and b_rate > 0:
            p_val = stats.binomtest(p_cnt, len(pdf), b_rate).pvalue
            p_pct = p_cnt / len(pdf) * 100
            b_pct = b_rate * 100
            if p_val < 0.10:
                findings.append((name, p_pct, b_pct, p_val, "binary"))

    # Комбинации
    for r in combo_results:
        if r["p_value"] < 0.05:
            findings.append((r["combo"], r["pivot_pct"], r["base_pct"], r["p_value"], "combo"))

    # Элементы
    for el in ["Огонь", "Земля", "Воздух", "Вода"]:
        p_cnt = (pdf["moon_element"] == el).sum()
        b_rate = (bdf["moon_element"] == el).mean()
        if p_cnt > 0 and b_rate > 0:
            p_val = stats.binomtest(p_cnt, len(pdf), b_rate).pvalue
            if p_val < 0.10:
                findings.append((f"Луна в {el}", p_cnt / len(pdf) * 100, b_rate * 100, p_val, "element"))

    # Лунные дни
    for day in range(1, 31):
        p_cnt = (pdf["lunar_day"] == day).sum()
        b_rate = (bdf["lunar_day"] == day).mean()
        if p_cnt >= 4 and b_rate > 0:
            p = stats.binomtest(p_cnt, len(pdf), b_rate).pvalue
            if p < 0.05:
                findings.append((f"Лунный день {day}", p_cnt / len(pdf) * 100, b_rate * 100, p, "lunar_day"))

    findings.sort(key=lambda x: x[3])

    n_tests = len(binary_tests) + len(combo_results) + 4 + 30  # прибл. кол-во тестов
    bonferroni = 0.05 / n_tests

    if findings:
        print(f"\n  Всего тестов: ~{n_tests}")
        print(f"  Бонферрони порог: α = {bonferroni:.5f}")
        print(f"\n  {'Фактор':<50} {'Разв%':>7} {'Base%':>7} {'p-value':>10} {'Тип':<10}")
        print("  " + "-" * 90)
        for name, pct, base, p, ftype in findings:
            sig = "***" if p < bonferroni else "**" if p < 0.01 else "*" if p < 0.05 else "~"
            print(f"  {name:<50} {pct:>5.1f}% {base:>5.1f}% {p:>10.4f} {sig:<4} {ftype}")

        survived = [f for f in findings if f[3] < bonferroni]
        if survived:
            print(f"\n  === ВЫЖИЛИ ПОСЛЕ БОНФЕРРОНИ (α={bonferroni:.5f}) ===")
            for name, pct, base, p, ftype in survived:
                ratio = pct / max(base, 0.1)
                print(f"    {name}: {pct:.1f}% vs {base:.1f}% (ratio {ratio:.2f}x) p={p:.6f}")
        else:
            print(f"\n  После Бонферрони ничего не выжило.")

        # Практическое резюме
        print(f"\n  --- ПРАКТИЧЕСКОЕ РЕЗЮМЕ ---")
        strong = [f for f in findings if f[3] < 0.01]
        moderate = [f for f in findings if 0.01 <= f[3] < 0.05]
        weak = [f for f in findings if 0.05 <= f[3] < 0.10]

        if strong:
            print(f"\n  Сильные (p < 0.01):")
            for name, pct, base, p, _ in strong:
                print(f"    • {name}: {pct:.1f}% vs {base:.1f}% (p={p:.4f})")
        if moderate:
            print(f"\n  Умеренные (0.01 < p < 0.05):")
            for name, pct, base, p, _ in moderate:
                print(f"    • {name}: {pct:.1f}% vs {base:.1f}% (p={p:.4f})")
        if weak:
            print(f"\n  Слабые / тренды (0.05 < p < 0.10):")
            for name, pct, base, p, _ in weak:
                print(f"    • {name}: {pct:.1f}% vs {base:.1f}% (p={p:.4f})")
    else:
        print("\n  Значимых находок не обнаружено.")

    print("\n  ⚠ Корреляция ≠ причинность. Множественное тестирование увеличивает ложноположительные.")


def save_to_db(pdf, bdf):
    """Сохраняем расширенные астро-данные в SQLite."""
    conn = sqlite3.connect(DB_PATH)

    # Таблица расширенных астро-данных для разворотов
    pivot_rows = []
    for _, row in pdf.iterrows():
        pivot_rows.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "price": row["price"],
            "pivot_type": row["pivot_type"],
            "pct_change": row["pct_change"],
            "is_high": int(row["is_high"]),
            "is_major": int(row["is_major"]),
            "moon_phase": row["moon_phase"],
            "moon_quarter": row["moon_quarter"],
            "lunar_day": row["lunar_day"],
            "moon_sign": row["moon_sign"],
            "moon_element": row["moon_element"],
            "moon_modality": row["moon_modality"],
            "sun_sign": row["sun_sign"],
            "sun_element": row["sun_element"],
            "jupiter_sign": row["jupiter_sign"],
            "saturn_sign": row["saturn_sign"],
            "mars_sign": row["mars_sign"],
            "venus_sign": row["venus_sign"],
            "rahu_sign": row["rahu_sign"],
            "ketu_sign": row["ketu_sign"],
            "near_node": int(row["near_node"]),
            "near_rahu": int(row["near_rahu"]),
            "near_ketu": int(row["near_ketu"]),
            "moon_rahu_dist": row["moon_rahu_dist"],
            "mercury_retro": int(row["mercury_retro"]),
            "venus_retro": int(row["venus_retro"]),
            "mars_retro": int(row["mars_retro"]),
            "jupiter_retro": int(row["jupiter_retro"]),
            "saturn_retro": int(row["saturn_retro"]),
            "retro_count": row["retro_count"],
            "any_station": int(row["any_station"]),
            "voc": int(row["voc"]),
            "any_ingress": int(row["any_ingress"]),
            "moon_ingress": int(row["moon_ingress_flag"]),
            "n_aspects": row["n_aspects"],
            "tension_count": row["tension_count"],
            "harmony_count": row["harmony_count"],
            "tension_ratio": row["tension_ratio"],
            "eclipse_days": row["eclipse_days"],
            "near_eclipse": int(row["near_eclipse"]),
            "aspects": "|".join(row["aspects"]),
        })

    pivot_df = pd.DataFrame(pivot_rows)
    pivot_df.to_sql("btc_pivot_astro_v2", conn, if_exists="replace", index=False)
    print(f"\nСохранено в btc_pivot_astro_v2: {len(pivot_df)} строк")

    # Таблица baseline
    base_rows = []
    for _, row in bdf.iterrows():
        base_rows.append({
            "moon_quarter": row["moon_quarter"],
            "lunar_day": row["lunar_day"],
            "moon_sign": row["moon_sign"],
            "moon_element": row["moon_element"],
            "moon_modality": row["moon_modality"],
            "sun_sign": row["sun_sign"],
            "rahu_sign": row["rahu_sign"],
            "near_node": int(row["near_node"]),
            "near_rahu": int(row["near_rahu"]),
            "near_ketu": int(row["near_ketu"]),
            "moon_rahu_dist": row["moon_rahu_dist"],
            "mercury_retro": int(row["mercury_retro"]),
            "venus_retro": int(row["venus_retro"]),
            "mars_retro": int(row["mars_retro"]),
            "jupiter_retro": int(row["jupiter_retro"]),
            "saturn_retro": int(row["saturn_retro"]),
            "retro_count": row["retro_count"],
            "any_station": int(row["any_station"]),
            "voc": int(row["voc"]),
            "any_ingress": int(row["any_ingress"]),
            "moon_ingress": int(row["moon_ingress_flag"]),
            "n_aspects": row["n_aspects"],
            "tension_count": row["tension_count"],
            "harmony_count": row["harmony_count"],
            "tension_ratio": row["tension_ratio"],
            "eclipse_days": row["eclipse_days"],
            "near_eclipse": int(row["near_eclipse"]),
        })

    base_df = pd.DataFrame(base_rows)
    base_df.to_sql("btc_baseline_astro_v2", conn, if_exists="replace", index=False)
    print(f"Сохранено в btc_baseline_astro_v2: {len(base_df)} строк")

    conn.close()


def main():
    pivots, all_days = load_data()
    print(f"Загружено: {len(pivots)} разворотов, {len(all_days)} торговых дней")

    if len(pivots) == 0 or len(all_days) == 0:
        print("Нет данных.")
        return

    pdf, bdf = compute_datasets(pivots, all_days)

    # Сохраняем в БД
    save_to_db(pdf, bdf)

    # Все анализы
    analyze_lunar_nodes(pdf, bdf)
    analyze_voc(pdf, bdf)
    analyze_ingresses(pdf, bdf)
    analyze_elements(pdf, bdf)
    combo_results = analyze_extended_combos(pdf, bdf)
    analyze_highs_vs_lows_extended(pdf)
    analyze_node_aspects(pdf, bdf)
    analyze_timing_patterns(pdf)

    # Визуализация
    plot_extended_results(pdf, bdf, combo_results)

    # Вердикт
    print_verdict(pdf, bdf, combo_results)


if __name__ == "__main__":
    main()
