"""
BTC Пики vs Дно x Астрология — Корреляционный анализ
Полный период 2016-2026. Ищем астро-условия, которые статистически
чаще совпадают с пиками vs дном.
"""

import sqlite3
import math
from collections import Counter
from datetime import datetime, timedelta

import ephem
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

try:
    from .astro_shared import (
        DB_PATH, ECLIPSE_DATES, ZODIAC_SIGNS, ELEMENT_MAP, MODALITY_MAP,
        get_zodiac_sign, apply_bh_correction,
    )
except ImportError:
    from astro_shared import (
        DB_PATH, ECLIPSE_DATES, ZODIAC_SIGNS, ELEMENT_MAP, MODALITY_MAP,
        get_zodiac_sign, apply_bh_correction,
    )


# ── Конфигурация ─────────────────────────────────────────────────────
START_DATE = "2016-01-01"
END_DATE = "2026-03-11"
STATION_WINDOW = 5       # дней для определения стационарности
ECLIPSE_WINDOW = 7       # ±дней для «рядом с затмением»
ASPECT_DEFS = {
    "соединение": (0, 8),
    "секстиль": (60, 6),
    "квадратура": (90, 8),
    "трин": (120, 8),
    "оппозиция": (180, 8),
}
SLOW_PLANETS = {
    "Юпитер": ephem.Jupiter,
    "Сатурн": ephem.Saturn,
}
PERSONAL_PLANETS = {
    "Меркурий": ephem.Mercury,
    "Венера": ephem.Venus,
    "Марс": ephem.Mars,
}
ALL_PLANETS = {
    "Солнце": ephem.Sun,
    "Луна": ephem.Moon,
    **PERSONAL_PLANETS,
    **SLOW_PLANETS,
}


# ── Утилиты ──────────────────────────────────────────────────────────

def _lon_deg(body_cls, d):
    return float(ephem.Ecliptic(body_cls(d)).lon) * 180 / math.pi


def _is_retrograde(body_cls, d):
    d_prev = ephem.Date(d - 1)
    lon_now = _lon_deg(body_cls, d)
    lon_prev = _lon_deg(body_cls, d_prev)
    diff = lon_now - lon_prev
    if diff > 180:
        diff -= 360
    elif diff < -180:
        diff += 360
    return diff < 0


def _is_stationary(body_cls, d, orb_days=2):
    def lon(dt):
        return _lon_deg(body_cls, dt)

    def norm(a, b):
        diff = a - b
        if diff > 180: diff -= 360
        elif diff < -180: diff += 360
        return diff

    d_before = ephem.Date(d - orb_days)
    d_after = ephem.Date(d + orb_days)
    dir_before = norm(lon(d), lon(d_before))
    dir_after = norm(lon(d_after), lon(d))
    return (dir_before > 0 and dir_after < 0) or (dir_before < 0 and dir_after > 0)


def _near_station(body_cls, date, window=STATION_WINDOW):
    for offset in range(-window, window + 1):
        if _is_stationary(body_cls, ephem.Date(date + timedelta(days=offset))):
            return True
    return False


def _angular_dist(a, b):
    diff = abs((a - b) % 360)
    return min(diff, 360 - diff)


# ── Полный астро-профиль ─────────────────────────────────────────────

def compute_astro(date: datetime) -> dict:
    d = ephem.Date(date)
    moon = ephem.Moon(d)

    # Луна
    moon_lon = _lon_deg(ephem.Moon, d)
    moon_sign = get_zodiac_sign(moon_lon)

    phase = moon.phase / 100.0
    prev_new = ephem.previous_new_moon(d)
    next_new = ephem.next_new_moon(d)
    cycle_len = next_new - prev_new
    position = (d - prev_new) / cycle_len

    if position < 0.125 or position >= 0.875:
        quarter = "Новолуние"
    elif position < 0.375:
        quarter = "Растущая"
    elif position < 0.625:
        quarter = "Полнолуние"
    else:
        quarter = "Убывающая"

    new_moon_days = min(abs(d - prev_new), abs(next_new - d))
    prev_full = ephem.previous_full_moon(d)
    next_full = ephem.next_full_moon(d)
    full_moon_days = min(abs(d - prev_full), abs(next_full - d))

    # Планеты — позиции и знаки
    planet_lons = {}
    planet_signs = {}
    for name, cls in ALL_PLANETS.items():
        lon = _lon_deg(cls, d)
        planet_lons[name] = lon
        planet_signs[name] = get_zodiac_sign(lon)

    # Ретроградность
    retro = {}
    for name, cls in {**PERSONAL_PLANETS, **SLOW_PLANETS}.items():
        retro[name] = _is_retrograde(cls, d)
    retro_count = sum(retro.values())

    # Станции
    stations = {}
    for name, cls in PERSONAL_PLANETS.items():
        stations[name] = _near_station(cls, date)
    any_station = any(stations.values())

    # Аспекты
    body_names = list(planet_lons.keys())
    aspects = []
    tension_count = 0
    harmony_count = 0
    for i in range(len(body_names)):
        for j in range(i + 1, len(body_names)):
            b1, b2 = body_names[i], body_names[j]
            dist = _angular_dist(planet_lons[b1], planet_lons[b2])
            for asp_name, (angle, orb) in ASPECT_DEFS.items():
                if abs(dist - angle) <= orb:
                    aspects.append(f"{b1}-{b2} {asp_name}")
                    if asp_name in ("квадратура", "оппозиция"):
                        tension_count += 1
                    elif asp_name in ("трин", "секстиль"):
                        harmony_count += 1

    # Затмения
    eclipse_days = min(abs((date - ed).days) for ed in ECLIPSE_DATES)

    return {
        "moon_phase": round(phase, 3),
        "moon_quarter": quarter,
        "moon_sign": moon_sign,
        "moon_element": ELEMENT_MAP[moon_sign],
        "moon_modality": MODALITY_MAP[moon_sign],
        "new_moon_days": round(float(new_moon_days), 1),
        "full_moon_days": round(float(full_moon_days), 1),
        "sun_sign": planet_signs["Солнце"],
        "mars_sign": planet_signs.get("Марс"),
        "jupiter_sign": planet_signs.get("Юпитер"),
        "saturn_sign": planet_signs.get("Сатурн"),
        "mercury_retro": retro.get("Меркурий", False),
        "venus_retro": retro.get("Венера", False),
        "mars_retro": retro.get("Марс", False),
        "jupiter_retro": retro.get("Юпитер", False),
        "saturn_retro": retro.get("Сатурн", False),
        "retro_count": retro_count,
        "any_station": any_station,
        "mercury_station": stations.get("Меркурий", False),
        "venus_station": stations.get("Венера", False),
        "mars_station": stations.get("Марс", False),
        "n_aspects": len(aspects),
        "tension_count": tension_count,
        "harmony_count": harmony_count,
        "tension_ratio": round(tension_count / max(tension_count + harmony_count, 1), 3),
        "eclipse_days": eclipse_days,
        "near_eclipse": eclipse_days <= ECLIPSE_WINDOW,
        "aspects": aspects,
    }


# ── Загрузка данных ──────────────────────────────────────────────────

def load_data():
    conn = sqlite3.connect(DB_PATH)
    pivots = pd.read_sql(
        f"SELECT date, price, type, pct_change FROM btc_pivots "
        f"WHERE date >= '{START_DATE}' AND date <= '{END_DATE}' ORDER BY date",
        conn,
    )
    all_days = pd.read_sql(
        f"SELECT date, close FROM btc_daily "
        f"WHERE date >= '{START_DATE}' AND date <= '{END_DATE}' ORDER BY date",
        conn,
    )
    conn.close()
    pivots["date"] = pd.to_datetime(pivots["date"])
    all_days["date"] = pd.to_datetime(all_days["date"])
    return pivots, all_days


# ── Статистика ───────────────────────────────────────────────────────

def binomial_test(hits, total, base_rate):
    if base_rate <= 0 or base_rate >= 1:
        return 1.0
    return stats.binomtest(int(hits), int(total), float(base_rate)).pvalue


def compare_categorical(pivot_series, baseline_series, categories, label,
                         high_series=None, low_series=None):
    """Сравнивает распределение категориальной переменной."""
    pivot_counts = Counter(pivot_series)
    base_counts = Counter(baseline_series)
    n_pivot = len(pivot_series)
    n_base = len(baseline_series)

    print(f"\n{'─' * 70}")
    print(f"  {label}")
    print(f"{'─' * 70}")

    header = f"  {'Категория':<16} {'Пики':>12} {'Дно':>12} {'Все pivots':>12} {'Baseline':>10} {'p-val':>8}"
    print(header)

    rows = []
    for cat in categories:
        p_cnt = pivot_counts.get(cat, 0)
        p_pct = p_cnt / max(n_pivot, 1) * 100
        b_pct = base_counts.get(cat, 0) / max(n_base, 1) * 100

        h_str = l_str = ""
        if high_series is not None:
            h_cnt = Counter(high_series).get(cat, 0)
            h_pct = h_cnt / max(len(high_series), 1) * 100
            h_str = f"{h_cnt:>4} ({h_pct:>4.1f}%)"
        if low_series is not None:
            l_cnt = Counter(low_series).get(cat, 0)
            l_pct = l_cnt / max(len(low_series), 1) * 100
            l_str = f"{l_cnt:>4} ({l_pct:>4.1f}%)"

        p_val = binomial_test(p_cnt, n_pivot, base_counts.get(cat, 0) / max(n_base, 1))
        sig = " *" if p_val < 0.05 else " ~" if p_val < 0.10 else ""

        print(f"  {cat:<16} {h_str:>12} {l_str:>12} {p_cnt:>4} ({p_pct:>4.1f}%) "
              f"{b_pct:>8.1f}% {p_val:>8.4f}{sig}")
        rows.append({"cat": cat, "pivot_pct": p_pct, "base_pct": b_pct, "p_val": p_val})

    # Хи-квадрат
    obs = np.array([pivot_counts.get(c, 0) for c in categories])
    exp_raw = np.array([base_counts.get(c, 0) for c in categories])
    mask = (obs + exp_raw) > 0
    if mask.sum() >= 2 and obs[mask].sum() > 0 and exp_raw[mask].sum() > 0:
        exp_scaled = exp_raw[mask] / exp_raw[mask].sum() * obs[mask].sum()
        chi2, p_chi = stats.chisquare(obs[mask], exp_scaled)
        print(f"\n  χ² = {chi2:.2f}, p = {p_chi:.4f}")
    else:
        chi2, p_chi = None, None

    return rows, chi2, p_chi


def compare_binary(pivot_series, baseline_series, label,
                    high_series=None, low_series=None):
    """Сравнивает бинарную переменную (True/False)."""
    p_rate = pivot_series.mean() * 100
    b_rate = baseline_series.mean() * 100
    p_val = binomial_test(int(pivot_series.sum()), len(pivot_series), baseline_series.mean())

    h_str = l_str = ""
    if high_series is not None:
        h_rate = high_series.mean() * 100
        h_str = f"Пики={h_rate:.1f}%"
    if low_series is not None:
        l_rate = low_series.mean() * 100
        l_str = f"Дно={l_rate:.1f}%"

    sig = " *" if p_val < 0.05 else " ~" if p_val < 0.10 else ""
    diff = p_rate - b_rate
    print(f"  {label:<30} Pivots={p_rate:>5.1f}%  {h_str:>14}  {l_str:>14}  "
          f"Base={b_rate:>5.1f}%  Δ={diff:>+5.1f}%  p={p_val:.4f}{sig}")
    return {"label": label, "pivot": p_rate, "base": b_rate, "diff": diff, "p": p_val}


# ── Главный анализ ───────────────────────────────────────────────────

def main():
    pivots_raw, all_days = load_data()
    print(f"Pivot-точки: {len(pivots_raw)}  |  Торговых дней: {len(all_days)}  |  "
          f"Период: {START_DATE} — {END_DATE}")

    # Разделяем пики и дно
    highs_raw = pivots_raw[pivots_raw["type"].str.contains("high")]
    lows_raw = pivots_raw[pivots_raw["type"].str.contains("low")]
    major_raw = pivots_raw[pivots_raw["type"].str.contains("major|global")]
    print(f"Пики: {len(highs_raw)}  |  Дно: {len(lows_raw)}  |  Major: {len(major_raw)}")

    # ── Астро для всех pivot-точек ────────────────────────────────────
    print("\nВычисление астро-профилей для pivot-точек...")
    pivot_records = []
    for i, (_, row) in enumerate(pivots_raw.iterrows()):
        rec = compute_astro(row["date"].to_pydatetime())
        rec["date"] = row["date"]
        rec["price"] = row["price"]
        rec["type"] = row["type"]
        rec["pct_change"] = row["pct_change"]
        rec["is_high"] = "high" in row["type"]
        rec["is_major"] = "major" in row["type"] or "global" in row["type"]
        pivot_records.append(rec)
        if (i + 1) % 20 == 0:
            print(f"  pivots: {i + 1}/{len(pivots_raw)}")

    pdf = pd.DataFrame(pivot_records)
    highs = pdf[pdf["is_high"]]
    lows = pdf[~pdf["is_high"]]
    majors = pdf[pdf["is_major"]]

    # ── Baseline (сэмпл ~25% обычных дней) ───────────────────────────
    print("Вычисление baseline астро...")
    pivot_date_set = set(pivots_raw["date"])
    non_pivot_days = all_days[~all_days["date"].isin(pivot_date_set)]
    sample = non_pivot_days.sample(frac=0.25, random_state=42)
    base_records = []
    for i, (_, row) in enumerate(sample.iterrows()):
        rec = compute_astro(row["date"].to_pydatetime())
        base_records.append(rec)
        if (i + 1) % 100 == 0:
            print(f"  baseline: {i + 1}/{len(sample)}")

    bdf = pd.DataFrame(base_records)

    # ══════════════════════════════════════════════════════════════════
    #  ОТЧЁТ
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print(f"  BTC ПИКИ vs ДНО x АСТРОЛОГИЯ — КОРРЕЛЯЦИОННЫЙ АНАЛИЗ ({START_DATE}—{END_DATE})")
    print("=" * 90)

    # ── 1. Фазы Луны ─────────────────────────────────────────────────
    quarters = ["Новолуние", "Растущая", "Полнолуние", "Убывающая"]
    moon_rows, chi2_moon, p_moon = compare_categorical(
        pdf["moon_quarter"], bdf["moon_quarter"], quarters,
        "1. ФАЗЫ ЛУНЫ", highs["moon_quarter"], lows["moon_quarter"],
    )

    # Отдельно: пики vs дно (Fisher exact для каждой фазы)
    print("\n  Пики vs Дно по фазам (Fisher exact):")
    for q in quarters:
        h_in = (highs["moon_quarter"] == q).sum()
        h_out = len(highs) - h_in
        l_in = (lows["moon_quarter"] == q).sum()
        l_out = len(lows) - l_in
        _, p_fisher = stats.fisher_exact([[h_in, h_out], [l_in, l_out]])
        h_pct = h_in / len(highs) * 100
        l_pct = l_in / len(lows) * 100
        sig = " *" if p_fisher < 0.05 else ""
        print(f"    {q:<14}  Пики={h_pct:>5.1f}%  Дно={l_pct:>5.1f}%  p={p_fisher:.4f}{sig}")

    # ── 2. Знаки Луны ────────────────────────────────────────────────
    sign_rows, chi2_sign, p_sign = compare_categorical(
        pdf["moon_sign"], bdf["moon_sign"], ZODIAC_SIGNS,
        "2. ЗНАКИ ЛУНЫ", highs["moon_sign"], lows["moon_sign"],
    )

    # ── 3. Элементы Луны ─────────────────────────────────────────────
    elements = ["Огонь", "Земля", "Воздух", "Вода"]
    elem_rows, chi2_elem, p_elem = compare_categorical(
        pdf["moon_element"], bdf["moon_element"], elements,
        "3. ЭЛЕМЕНТ ЛУНЫ", highs["moon_element"], lows["moon_element"],
    )

    # ── 4. Бинарные признаки ─────────────────────────────────────────
    print(f"\n{'─' * 70}")
    print("  4. БИНАРНЫЕ АСТРО-ПРИЗНАКИ")
    print(f"{'─' * 70}")

    binary_results = []
    for col, label in [
        ("mercury_retro", "Меркурий ретро"),
        ("venus_retro", "Венера ретро"),
        ("mars_retro", "Марс ретро"),
        ("jupiter_retro", "Юпитер ретро"),
        ("saturn_retro", "Сатурн ретро"),
        ("any_station", f"Любая станция ±{STATION_WINDOW}д"),
        ("mercury_station", f"Станция Меркурия ±{STATION_WINDOW}д"),
        ("near_eclipse", f"Затмение ±{ECLIPSE_WINDOW}д"),
    ]:
        r = compare_binary(
            pdf[col], bdf[col], label,
            highs[col], lows[col],
        )
        binary_results.append(r)

    # ── 5. Аспекты напряжения vs гармонии ─────────────────────────────
    print(f"\n{'─' * 70}")
    print("  5. АСПЕКТЫ: НАПРЯЖЕНИЕ vs ГАРМОНИЯ")
    print(f"{'─' * 70}")

    for label, col in [("Напряжённых аспектов", "tension_count"),
                        ("Гармоничных аспектов", "harmony_count"),
                        ("Tension ratio", "tension_ratio")]:
        p_mean = pdf[col].mean()
        h_mean = highs[col].mean()
        l_mean = lows[col].mean()
        b_mean = bdf[col].mean()
        _, mw_p = stats.mannwhitneyu(pdf[col], bdf[col], alternative="two-sided")
        # Пики vs Дно
        _, hl_p = stats.mannwhitneyu(highs[col], lows[col], alternative="two-sided")
        sig_bl = " *" if mw_p < 0.05 else ""
        sig_hl = " *" if hl_p < 0.05 else ""
        print(f"  {label:<26} Pivots={p_mean:.2f}  Пики={h_mean:.2f}  Дно={l_mean:.2f}  "
              f"Base={b_mean:.2f}  p(vs base)={mw_p:.4f}{sig_bl}  p(пик vs дно)={hl_p:.4f}{sig_hl}")

    # ── 6. Конкретные аспекты: частота при пиках vs дно ────────────────
    print(f"\n{'─' * 70}")
    print("  6. КОНКРЕТНЫЕ АСПЕКТЫ: ПИКИ vs ДНО")
    print(f"{'─' * 70}")

    high_asp_counter = Counter()
    low_asp_counter = Counter()
    base_asp_counter = Counter()
    for aspects in highs["aspects"]:
        high_asp_counter.update(aspects)
    for aspects in lows["aspects"]:
        low_asp_counter.update(aspects)
    for aspects in bdf["aspects"]:
        base_asp_counter.update(aspects)

    # Все уникальные аспекты
    all_asp = set(high_asp_counter) | set(low_asp_counter)
    aspect_stats = []
    for asp in all_asp:
        h_cnt = high_asp_counter[asp]
        l_cnt = low_asp_counter[asp]
        b_rate = base_asp_counter[asp] / max(len(bdf), 1)
        h_pct = h_cnt / max(len(highs), 1) * 100
        l_pct = l_cnt / max(len(lows), 1) * 100
        b_pct = b_rate * 100

        # Fisher: пики vs дно
        h_no = len(highs) - h_cnt
        l_no = len(lows) - l_cnt
        if h_cnt + l_cnt >= 3:
            _, p_f = stats.fisher_exact([[h_cnt, h_no], [l_cnt, l_no]])
        else:
            p_f = 1.0

        aspect_stats.append({
            "aspect": asp, "high_pct": h_pct, "low_pct": l_pct,
            "base_pct": b_pct, "diff_hl": h_pct - l_pct, "p_fisher": p_f,
        })

    aspect_stats.sort(key=lambda x: x["p_fisher"])
    apply_bh_correction(aspect_stats, p_key="p_fisher", q_key="q_fisher")

    print(f"\n  {'Аспект':<32} {'Пики%':>7} {'Дно%':>7} {'Base%':>7} {'Δ(П-Д)':>8} {'p':>8} {'q':>8}")
    for row in aspect_stats[:25]:
        sig = " *" if row["q_fisher"] < 0.10 else ""
        print(f"  {row['aspect']:<32} {row['high_pct']:>6.1f}% {row['low_pct']:>6.1f}% "
              f"{row['base_pct']:>6.1f}% {row['diff_hl']:>+7.1f}% {row['p_fisher']:>8.4f} "
              f"{row['q_fisher']:>8.4f}{sig}")

    # ── 7. Знак Солнца (сезонность) ──────────────────────────────────
    sun_rows, chi2_sun, p_sun = compare_categorical(
        pdf["sun_sign"], bdf["sun_sign"], ZODIAC_SIGNS,
        "7. ЗНАК СОЛНЦА (СЕЗОННОСТЬ)", highs["sun_sign"], lows["sun_sign"],
    )

    # ── 8. Major развороты: детальный профиль ─────────────────────────
    print(f"\n{'─' * 70}")
    print("  8. АСТРО-ПРОФИЛЬ КРУПНЫХ РАЗВОРОТОВ (major + global)")
    print(f"{'─' * 70}")

    print(f"\n  {'Дата':<12} {'$':>10} {'Тип':<14} {'Луна':<12} {'☽знак':<10} "
          f"{'Hg℞':>5} {'♃℞':>5} {'♄℞':>5} {'Затм':>5} {'T/H':>5} {'Аспекты ключевые'}")
    for _, row in majors.iterrows():
        hg = "да" if row["mercury_retro"] else "-"
        ju = "да" if row["jupiter_retro"] else "-"
        sa = "да" if row["saturn_retro"] else "-"
        ecl = f"{row['eclipse_days']}д" if row["eclipse_days"] <= 14 else "-"
        th = f"{row['tension_count']}/{row['harmony_count']}"
        # Показываем только аспекты с медленными планетами
        slow_aspects = [a for a in row["aspects"]
                        if any(p in a for p in ("Юпитер", "Сатурн"))]
        asp_str = ", ".join(slow_aspects[:3])
        if len(slow_aspects) > 3:
            asp_str += f" +{len(slow_aspects) - 3}"
        direction = "▲" if row["is_high"] else "▼"
        print(f"  {row['date'].strftime('%Y-%m-%d'):<12} ${row['price']:>9,.0f} "
              f"{direction} {row['type']:<12} {row['moon_quarter']:<12} {row['moon_sign']:<10} "
              f"{hg:>5} {ju:>5} {sa:>5} {ecl:>5} {th:>5} {asp_str}")

    # ── 9. Сводная таблица значимых корреляций ────────────────────────
    print(f"\n{'═' * 90}")
    print("  СВОДКА: ВСЕ СТАТИСТИЧЕСКИ ЗНАЧИМЫЕ КОРРЕЛЯЦИИ (p < 0.10)")
    print(f"{'═' * 90}")

    significant = []
    for r in binary_results:
        if r["p"] < 0.10:
            significant.append(r)
    significant.sort(key=lambda x: x["p"])

    if significant:
        print(f"\n  {'Признак':<30} {'Pivots%':>8} {'Base%':>8} {'Δ':>7} {'p-value':>10}")
        for s in significant:
            print(f"  {s['label']:<30} {s['pivot']:>7.1f}% {s['base']:>7.1f}% "
                  f"{s['diff']:>+6.1f}% {s['p']:>10.4f}")
    else:
        print("\n  Нет бинарных признаков с p < 0.10")

    sig_aspects = [a for a in aspect_stats if a["q_fisher"] < 0.15]
    if sig_aspects:
        print(f"\n  Аспекты различающие пики от дна (q < 0.15):")
        for a in sig_aspects:
            print(f"    {a['aspect']:<32} Пики={a['high_pct']:.1f}%  Дно={a['low_pct']:.1f}%  "
                  f"q={a['q_fisher']:.4f}")

    # ══════════════════════════════════════════════════════════════════
    #  ВИЗУАЛИЗАЦИЯ
    # ══════════════════════════════════════════════════════════════════
    fig, axes = plt.subplots(3, 3, figsize=(24, 20))

    # 1. Фазы Луны: Пики vs Дно vs Baseline
    ax = axes[0, 0]
    x = np.arange(len(quarters))
    w = 0.25
    h_pcts = [Counter(highs["moon_quarter"]).get(q, 0) / max(len(highs), 1) * 100 for q in quarters]
    l_pcts = [Counter(lows["moon_quarter"]).get(q, 0) / max(len(lows), 1) * 100 for q in quarters]
    b_pcts = [Counter(bdf["moon_quarter"]).get(q, 0) / max(len(bdf), 1) * 100 for q in quarters]
    ax.bar(x - w, h_pcts, w, label="Пики", color="#FF6B6B", edgecolor="black", linewidth=0.5)
    ax.bar(x, l_pcts, w, label="Дно", color="#4ECDC4", edgecolor="black", linewidth=0.5)
    ax.bar(x + w, b_pcts, w, label="Baseline", color="#95A5A6", edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(quarters, fontsize=9)
    ax.set_ylabel("%")
    ax.set_title("Фазы Луны: Пики vs Дно vs Baseline", fontweight="bold")
    ax.legend()

    # 2. Знаки Луны — разница пики-дно
    ax = axes[0, 1]
    h_sign = Counter(highs["moon_sign"])
    l_sign = Counter(lows["moon_sign"])
    diffs_sign = [(h_sign.get(s, 0) / max(len(highs), 1) - l_sign.get(s, 0) / max(len(lows), 1)) * 100
                  for s in ZODIAC_SIGNS]
    colors_sign = ["#FF6B6B" if d > 0 else "#4ECDC4" for d in diffs_sign]
    ax.barh(ZODIAC_SIGNS, diffs_sign, color=colors_sign, edgecolor="black", linewidth=0.5)
    ax.axvline(0, color="gray", linewidth=0.5)
    ax.set_xlabel("Δ(Пики% − Дно%)")
    ax.set_title("Знаки Луны: Пики vs Дно\n(>0 = чаще при пиках)", fontweight="bold")

    # 3. Элементы Луны
    ax = axes[0, 2]
    x = np.arange(len(elements))
    h_elem = [Counter(highs["moon_element"]).get(e, 0) / max(len(highs), 1) * 100 for e in elements]
    l_elem = [Counter(lows["moon_element"]).get(e, 0) / max(len(lows), 1) * 100 for e in elements]
    b_elem = [Counter(bdf["moon_element"]).get(e, 0) / max(len(bdf), 1) * 100 for e in elements]
    ax.bar(x - w, h_elem, w, label="Пики", color="#FF6B6B", edgecolor="black", linewidth=0.5)
    ax.bar(x, l_elem, w, label="Дно", color="#4ECDC4", edgecolor="black", linewidth=0.5)
    ax.bar(x + w, b_elem, w, label="Baseline", color="#95A5A6", edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(elements)
    ax.set_ylabel("%")
    ax.set_title("Элемент Луны: Пики vs Дно vs Baseline", fontweight="bold")
    ax.legend()

    # 4. Ретроградность — Пики vs Дно vs Baseline
    ax = axes[1, 0]
    retro_planets = ["Меркурий", "Венера", "Марс", "Юпитер", "Сатурн"]
    retro_cols = ["mercury_retro", "venus_retro", "mars_retro", "jupiter_retro", "saturn_retro"]
    x = np.arange(len(retro_planets))
    h_retro = [highs[c].mean() * 100 for c in retro_cols]
    l_retro = [lows[c].mean() * 100 for c in retro_cols]
    b_retro = [bdf[c].mean() * 100 for c in retro_cols]
    ax.bar(x - w, h_retro, w, label="Пики", color="#FF6B6B", edgecolor="black", linewidth=0.5)
    ax.bar(x, l_retro, w, label="Дно", color="#4ECDC4", edgecolor="black", linewidth=0.5)
    ax.bar(x + w, b_retro, w, label="Baseline", color="#95A5A6", edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(retro_planets, fontsize=9)
    ax.set_ylabel("% дней в ретрограде")
    ax.set_title("Ретроградность: Пики vs Дно vs Baseline", fontweight="bold")
    ax.legend()

    # 5. Tension vs Harmony scatter
    ax = axes[1, 1]
    ax.scatter(highs["tension_count"], highs["harmony_count"],
               c="#FF6B6B", s=50, alpha=0.7, label="Пики", edgecolors="black", linewidths=0.3)
    ax.scatter(lows["tension_count"], lows["harmony_count"],
               c="#4ECDC4", s=50, alpha=0.7, label="Дно", edgecolors="black", linewidths=0.3)
    ax.set_xlabel("Напряжённые аспекты")
    ax.set_ylabel("Гармоничные аспекты")
    ax.set_title("Tension vs Harmony при разворотах", fontweight="bold")
    ax.legend()

    # 6. Расстояние до затмения: Пики vs Дно
    ax = axes[1, 2]
    bins = np.arange(0, max(pdf["eclipse_days"].max(), 60) + 5, 5)
    ax.hist(highs["eclipse_days"], bins=bins, color="#FF6B6B", alpha=0.6,
            label="Пики", edgecolor="black", linewidth=0.3)
    ax.hist(lows["eclipse_days"], bins=bins, color="#4ECDC4", alpha=0.6,
            label="Дно", edgecolor="black", linewidth=0.3)
    ax.axvline(ECLIPSE_WINDOW, color="red", linestyle="--", label=f"±{ECLIPSE_WINDOW}д")
    ax.set_xlabel("Дней до ближайшего затмения")
    ax.set_ylabel("Кол-во")
    ax.set_title("Расстояние до затмений: Пики vs Дно", fontweight="bold")
    ax.legend()

    # 7. Знак Солнца (сезонность) — разница пики-дно
    ax = axes[2, 0]
    h_sun = Counter(highs["sun_sign"])
    l_sun = Counter(lows["sun_sign"])
    diffs_sun = [(h_sun.get(s, 0) / max(len(highs), 1) - l_sun.get(s, 0) / max(len(lows), 1)) * 100
                 for s in ZODIAC_SIGNS]
    colors_sun = ["#FF6B6B" if d > 0 else "#4ECDC4" for d in diffs_sun]
    ax.barh(ZODIAC_SIGNS, diffs_sun, color=colors_sun, edgecolor="black", linewidth=0.5)
    ax.axvline(0, color="gray", linewidth=0.5)
    ax.set_xlabel("Δ(Пики% − Дно%)")
    ax.set_title("Знак Солнца: Пики vs Дно\n(>0 = чаще пики в этом сезоне)", fontweight="bold")

    # 8. Тепловая карта: Знак Луны x Фаза Луны (пики)
    ax = axes[2, 1]
    heat_data_high = np.zeros((len(ZODIAC_SIGNS), len(quarters)))
    heat_data_low = np.zeros((len(ZODIAC_SIGNS), len(quarters)))
    for i, sign in enumerate(ZODIAC_SIGNS):
        for j, q in enumerate(quarters):
            heat_data_high[i, j] = ((highs["moon_sign"] == sign) & (highs["moon_quarter"] == q)).sum()
            heat_data_low[i, j] = ((lows["moon_sign"] == sign) & (lows["moon_quarter"] == q)).sum()
    # Разница: положительное = чаще при пиках
    heat_diff = heat_data_high - heat_data_low
    im = ax.imshow(heat_diff, cmap="RdYlGn_r", aspect="auto", interpolation="nearest")
    ax.set_xticks(range(len(quarters)))
    ax.set_xticklabels(quarters, fontsize=8)
    ax.set_yticks(range(len(ZODIAC_SIGNS)))
    ax.set_yticklabels(ZODIAC_SIGNS, fontsize=8)
    plt.colorbar(im, ax=ax, label="Пики − Дно (кол-во)")
    ax.set_title("Тепловая карта: Знак Луны × Фаза\n(красный = чаще пики)", fontweight="bold")
    # Аннотации
    for i in range(len(ZODIAC_SIGNS)):
        for j in range(len(quarters)):
            val = int(heat_diff[i, j])
            if val != 0:
                ax.text(j, i, str(val), ha="center", va="center", fontsize=7,
                        color="white" if abs(val) > 1 else "black")

    # 9. Кол-во ретроградных планет при пиках vs дно
    ax = axes[2, 2]
    retro_vals = sorted(pdf["retro_count"].unique())
    h_retro_dist = [Counter(highs["retro_count"]).get(v, 0) / max(len(highs), 1) * 100 for v in retro_vals]
    l_retro_dist = [Counter(lows["retro_count"]).get(v, 0) / max(len(lows), 1) * 100 for v in retro_vals]
    b_retro_dist = [Counter(bdf["retro_count"]).get(v, 0) / max(len(bdf), 1) * 100 for v in retro_vals]
    x = np.arange(len(retro_vals))
    ax.bar(x - w, h_retro_dist, w, label="Пики", color="#FF6B6B", edgecolor="black", linewidth=0.5)
    ax.bar(x, l_retro_dist, w, label="Дно", color="#4ECDC4", edgecolor="black", linewidth=0.5)
    ax.bar(x + w, b_retro_dist, w, label="Baseline", color="#95A5A6", edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(retro_vals)
    ax.set_xlabel("Кол-во ретроградных планет")
    ax.set_ylabel("%")
    ax.set_title("Кол-во ретроградных планет\nПики vs Дно vs Baseline", fontweight="bold")
    ax.legend()

    plt.suptitle(
        f"BTC Пики vs Дно × Астрология — Корреляции ({START_DATE}—{END_DATE})\n"
        f"Пики: {len(highs)} | Дно: {len(lows)} | Baseline: {len(bdf)} дней",
        fontsize=15, fontweight="bold", y=1.01,
    )
    plt.tight_layout()
    out_path = "astro_peak_low_correlation.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\nГрафик сохранён: {out_path}")
    plt.close()


if __name__ == "__main__":
    main()
