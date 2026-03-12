"""
BTC x Астрология: Глубокий анализ корреляций
Ищем комбинации факторов, раздельные паттерны пиков/дно,
окно ±3 дня, повторяющиеся астро-сигнатуры.
"""

import duckdb
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy import stats
from collections import Counter
from itertools import combinations
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from astro_shared import (
    DB_PATH, ECLIPSES, ECLIPSE_DATES, ZODIAC_SIGNS,
    apply_bh_correction, get_zodiac_sign,
    planet_lon_deg,
    moon_phase_percent,
    previous_new_moon, next_new_moon,
    is_retrograde as _is_retrograde,
    is_stationary as _is_stationary,
)


def get_full_astro(date):
    """Расширенный астро-профиль."""
    d = date
    d_prev = date - timedelta(days=1)

    # Фаза Луны
    phase = moon_phase_percent(d) / 100.0
    prev_new = previous_new_moon(d)
    next_new = next_new_moon(d)
    cycle_len = (next_new - prev_new).total_seconds()
    position = (d - prev_new).total_seconds() / cycle_len if cycle_len else 0

    if position < 0.125 or position >= 0.875:
        quarter = "Новолуние"
    elif 0.125 <= position < 0.375:
        quarter = "Растущая"
    elif 0.375 <= position < 0.625:
        quarter = "Полнолуние"
    else:
        quarter = "Убывающая"

    # Лунный день (1-30)
    lunar_day = int(position * 29.5) + 1

    moon_lon = planet_lon_deg("Луна", d)
    moon_sign = get_zodiac_sign(moon_lon)

    # Ретроградность
    mercury_retro = _is_retrograde("Меркурий", d, d_prev)
    venus_retro = _is_retrograde("Венера", d, d_prev)
    mars_retro = _is_retrograde("Марс", d, d_prev)
    jupiter_retro = _is_retrograde("Юпитер", d, d_prev)
    saturn_retro = _is_retrograde("Сатурн", d, d_prev)

    # Стационарность (±2 дня от смены направления)
    mercury_station = _is_stationary("Меркурий", d)
    venus_station = _is_stationary("Венера", d)
    mars_station = _is_stationary("Марс", d)
    jupiter_station = _is_stationary("Юпитер", d)
    saturn_station = _is_stationary("Сатурн", d)
    any_station = any([mercury_station, venus_station, mars_station, jupiter_station, saturn_station])

    # Позиции планет
    bodies = {
        "Луна": moon_lon,
        "Солнце": planet_lon_deg("Солнце", d),
        "Меркурий": planet_lon_deg("Меркурий", d),
        "Венера": planet_lon_deg("Венера", d),
        "Марс": planet_lon_deg("Марс", d),
        "Юпитер": planet_lon_deg("Юпитер", d),
        "Сатурн": planet_lon_deg("Сатурн", d),
    }

    sun_sign = get_zodiac_sign(bodies["Солнце"])
    jupiter_sign = get_zodiac_sign(bodies["Юпитер"])
    saturn_sign = get_zodiac_sign(bodies["Сатурн"])

    # Аспекты
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

    # Затмения
    min_eclipse_days = min(abs((date - ed).days) for ed in ECLIPSE_DATES)

    # Количество ретроградных планет
    retro_count = sum([mercury_retro, venus_retro, mars_retro, jupiter_retro, saturn_retro])

    # Напряжённые аспекты (квадратуры + оппозиции)
    tension_count = sum(1 for a in aspects if ":sq" in a or ":opp" in a)
    harmony_count = sum(1 for a in aspects if ":tri" in a or ":sext" in a)

    return {
        "moon_phase": round(phase, 3),
        "moon_quarter": quarter,
        "lunar_day": lunar_day,
        "moon_sign": moon_sign,
        "sun_sign": sun_sign,
        "jupiter_sign": jupiter_sign,
        "saturn_sign": saturn_sign,
        "mercury_retro": mercury_retro,
        "venus_retro": venus_retro,
        "mars_retro": mars_retro,
        "jupiter_retro": jupiter_retro,
        "saturn_retro": saturn_retro,
        "retro_count": retro_count,
        "any_station": any_station,
        "mercury_station": mercury_station,
        "venus_station": venus_station,
        "mars_station": mars_station,
        "jupiter_station": jupiter_station,
        "saturn_station": saturn_station,
        "eclipse_days": min_eclipse_days,
        "near_eclipse": min_eclipse_days <= 7,
        "aspects": aspects,
        "n_aspects": len(aspects),
        "tension_count": tension_count,
        "harmony_count": harmony_count,
        "tension_ratio": round(tension_count / max(len(aspects), 1), 3),
    }


# ============================================================
# ЗАГРУЗКА ДАННЫХ
# ============================================================

def load_data():
    conn = duckdb.connect(DB_PATH)
    pivots = pd.read_sql_query("""
        SELECT date, price, type, pct_change
        FROM btc_pivots
        ORDER BY date
    """, conn)
    all_days = pd.read_sql_query("""
        SELECT date, close
        FROM btc_daily
        ORDER BY date
    """, conn)
    conn.close()
    pivots["date"] = pd.to_datetime(pivots["date"])
    all_days["date"] = pd.to_datetime(all_days["date"])
    return pivots, all_days


def compute_astro_datasets(pivots, all_days):
    """Считает астро для разворотов и baseline."""
    print("Астро для разворотов...")
    pivot_records = []
    for _, row in pivots.iterrows():
        astro = get_full_astro(row["date"].to_pydatetime())
        astro["date"] = row["date"]
        astro["price"] = row["price"]
        astro["pivot_type"] = row["type"]
        astro["pct_change"] = row["pct_change"]
        astro["is_high"] = "high" in row["type"]
        astro["is_major"] = "major" in row["type"] or "global" in row["type"]
        pivot_records.append(astro)

    print("Астро для baseline (random sample ~33%)...")
    base_records = []
    for _, row in all_days.sample(frac=1/3, random_state=42).iterrows():
        astro = get_full_astro(row["date"].to_pydatetime())
        base_records.append(astro)
        if len(base_records) % 100 == 0:
            print(f"  {len(base_records)} дней...")

    return pd.DataFrame(pivot_records), pd.DataFrame(base_records)


# ============================================================
# АНАЛИЗ 1: КОМБИНАЦИИ ФАКТОРОВ
# ============================================================

def analyze_combinations(pdf, bdf):
    """Ищем комбинации 2-3 факторов которые чаще встречаются при разворотах."""
    print("\n" + "=" * 90)
    print("1. КОМБИНАЦИИ АСТРО-ФАКТОРОВ")
    print("=" * 90)

    # Создаём бинарные фичи
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
        f["high_tension"] = df["tension_count"] >= 3
        f["high_harmony"] = df["harmony_count"] >= 3
        f["many_retro"] = df["retro_count"] >= 2
        # Топ знаки Луны из предыдущего анализа
        for sign in ZODIAC_SIGNS:
            f[f"луна_{sign}"] = df["moon_sign"] == sign
        return f

    pf = make_features(pdf)
    bf = make_features(bdf)

    # Все пары факторов
    feature_cols = [c for c in pf.columns if not c.startswith("луна_")]
    core_features = feature_cols  # без знаков луны для пар

    results = []

    # Пары
    for f1, f2 in combinations(core_features, 2):
        p_both = (pf[f1] & pf[f2]).sum()
        b_both = (bf[f1] & bf[f2]).mean()

        if p_both < 3 or b_both < 0.01:
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

    # Фаза Луны + Знак Луны
    for quarter in ["новолуние", "полнолуние", "растущая", "убывающая"]:
        for sign in ZODIAC_SIGNS:
            sign_col = f"луна_{sign}"
            p_both = (pf[quarter] & pf[sign_col]).sum()
            b_both = (bf[quarter] & bf[sign_col]).mean()

            if p_both < 2 or b_both < 0.005:
                continue

            p_pct = p_both / len(pf) * 100
            b_pct = b_both * 100
            ratio = p_pct / max(b_pct, 0.1)

            if ratio > 2.0:
                p_val = stats.binomtest(int(p_both), len(pf), b_both).pvalue
                results.append({
                    "combo": f"{quarter} + Луна в {sign}",
                    "pivots": int(p_both),
                    "pivot_pct": round(p_pct, 1),
                    "base_pct": round(b_pct, 1),
                    "ratio": round(ratio, 2),
                    "p_value": round(p_val, 4),
                })

    apply_bh_correction(results)
    results.sort(key=lambda x: (x.get("q_value", 1.0), x["p_value"]))

    print(f"\nТоп комбинации (отклонение от baseline > 1.5x или < 0.5x):")
    print(f"{'Комбинация':<40} {'При разв.':>10} {'Base%':>8} {'Ratio':>7} {'p-value':>10} {'q-value':>10}")
    print("-" * 92)
    for r in results[:25]:
        q_value = r.get("q_value", 1.0)
        sig = " **" if q_value < 0.01 else " *" if q_value < 0.05 else ""
        print(f"{r['combo']:<40} {r['pivots']:>4} ({r['pivot_pct']:>4.1f}%) {r['base_pct']:>6.1f}% "
              f"{r['ratio']:>6.2f}x {r['p_value']:>10.4f} {q_value:>10.4f}{sig}")

    return results


# ============================================================
# АНАЛИЗ 2: ПИКИ vs ДНО — РАЗНЫЕ ПАТТЕРНЫ
# ============================================================

def analyze_highs_vs_lows(pdf, bdf):
    """Отдельный анализ паттернов для пиков и дно."""
    print("\n\n" + "=" * 90)
    print("2. ПИКИ vs ДНО — РАЗНЫЕ АСТРО-ПАТТЕРНЫ")
    print("=" * 90)

    highs = pdf[pdf["is_high"]]
    lows = pdf[~pdf["is_high"]]

    features = {
        "Фаза": "moon_quarter",
        "Знак Луны": "moon_sign",
        "Знак Солнца": "sun_sign",
    }

    for feat_name, col in features.items():
        print(f"\n--- {feat_name} ---")
        categories = pdf[col].unique()

        h_counts = Counter(highs[col])
        l_counts = Counter(lows[col])

        print(f"{'Значение':<16} {'Пики':>8} {'Дно':>8} {'Разница':>10} {'Перевес':>10}")
        interesting = []
        for cat in sorted(categories):
            h = h_counts.get(cat, 0)
            l = l_counts.get(cat, 0)
            h_pct = h / len(highs) * 100 if len(highs) > 0 else 0
            l_pct = l / len(lows) * 100 if len(lows) > 0 else 0
            diff = h_pct - l_pct

            if h + l == 0:
                continue

            direction = "ПИКИ" if diff > 5 else "ДНО" if diff < -5 else ""
            print(f"{cat:<16} {h:>3} ({h_pct:>4.1f}%) {l:>3} ({l_pct:>4.1f}%) {diff:>+8.1f}%  {direction:>10}")

            if abs(diff) > 5:
                interesting.append((cat, diff, direction))

        if interesting:
            print(f"\n  Заметные перекосы:")
            for cat, diff, direction in interesting:
                print(f"    {cat}: {diff:+.1f}% → чаще при {direction}")

    # Числовые факторы
    print(f"\n--- Числовые факторы: пики vs дно ---")
    num_features = [
        ("retro_count", "Кол-во ретро планет"),
        ("tension_count", "Напряжённые аспекты"),
        ("harmony_count", "Гармоничные аспекты"),
        ("tension_ratio", "Доля напряжённых"),
        ("eclipse_days", "Дней до затмения"),
        ("lunar_day", "Лунный день"),
        ("n_aspects", "Всего аспектов"),
    ]

    print(f"{'Фактор':<25} {'Пики (ср)':>12} {'Дно (ср)':>12} {'Разница':>10} {'p-value':>10}")
    for col, name in num_features:
        h_vals = highs[col].dropna()
        l_vals = lows[col].dropna()
        if len(h_vals) < 5 or len(l_vals) < 5:
            continue
        t, p = stats.ttest_ind(h_vals, l_vals)
        sig = " *" if p < 0.05 else ""
        print(f"{name:<25} {h_vals.mean():>12.3f} {l_vals.mean():>12.3f} "
              f"{h_vals.mean() - l_vals.mean():>+10.3f} {p:>10.4f}{sig}")


# ============================================================
# АНАЛИЗ 3: СТАЦИОНАРНЫЕ ПЛАНЕТЫ
# ============================================================

def analyze_stations(pdf, bdf):
    """Стационарные планеты при разворотах."""
    print("\n\n" + "=" * 90)
    print("3. СТАЦИОНАРНЫЕ ПЛАНЕТЫ (смена ретро↔директ)")
    print("=" * 90)

    station_records = []

    station_pivot = pdf["any_station"].sum()
    station_base = bdf["any_station"].mean() * 100
    station_pct = station_pivot / len(pdf) * 100

    p_val = stats.binomtest(int(station_pivot), len(pdf), bdf["any_station"].mean()).pvalue
    station_records.append({"name": "Любая планета", "p_cnt": int(station_pivot),
                            "p_pct": station_pct, "b_pct": station_base, "p_value": p_val,
                            "details": []})

    for planet, col in [
        ("Меркурий", "mercury_station"), ("Венера", "venus_station"),
        ("Марс", "mars_station"), ("Юпитер", "jupiter_station"), ("Сатурн", "saturn_station"),
    ]:
        p_cnt = pdf[col].sum()
        b_pct = bdf[col].mean() * 100
        p_pct = p_cnt / len(pdf) * 100
        if p_cnt > 0:
            p_v = stats.binomtest(int(p_cnt), len(pdf), max(bdf[col].mean(), 0.001)).pvalue
            details = []
            station_pivots = pdf[pdf[col]]
            for _, row in station_pivots.iterrows():
                details.append(f"    → {row['date'].strftime('%Y-%m-%d')} ${row['price']:,.0f} {row['pivot_type']}")
            station_records.append({"name": planet, "p_cnt": int(p_cnt),
                                    "p_pct": p_pct, "b_pct": b_pct, "p_value": p_v,
                                    "details": details})

    apply_bh_correction(station_records)

    for rec in station_records:
        sig = " *" if rec.get("q_value", 1.0) < 0.05 else ""
        if rec["name"] == "Любая планета":
            print(f"\n  Любая планета стационарная:")
            print(f"    При разворотах: {rec['p_cnt']}/{len(pdf)} ({rec['p_pct']:.1f}%)")
            print(f"    Baseline: {rec['b_pct']:.1f}%")
            print(f"    p-value: {rec['p_value']:.4f}  q-value: {rec['q_value']:.4f}{sig}")
        else:
            print(f"\n  {rec['name']} стационарный: {rec['p_cnt']}/{len(pdf)} ({rec['p_pct']:.1f}%) vs {rec['b_pct']:.1f}%  p={rec['p_value']:.4f}  q={rec['q_value']:.4f}{sig}")
            for line in rec["details"]:
                print(line)


# ============================================================
# АНАЛИЗ 4: ОКНО ±3 ДНЯ (РАЗМЫТИЕ)
# ============================================================

def analyze_window(pivots, all_days):
    """Смотрим астро не только в день разворота, но и ±3 дня."""
    print("\n\n" + "=" * 90)
    print("4. ОКНО ±3 ДНЯ — АСТРО-СОБЫТИЯ РЯДОМ С РАЗВОРОТОМ")
    print("=" * 90)

    events_near_pivots = []

    for _, row in pivots.iterrows():
        pivot_date = row["date"].to_pydatetime()
        for offset in range(-3, 4):
            check_date = pivot_date + timedelta(days=offset)
            astro = get_full_astro(check_date)

            if astro["any_station"]:
                station_planets = []
                for p, c in [("Hg", "mercury_station"), ("Ve", "venus_station"),
                             ("Ma", "mars_station"), ("Ju", "jupiter_station"), ("Sa", "saturn_station")]:
                    if astro[c]:
                        station_planets.append(p)
                events_near_pivots.append({
                    "pivot_date": row["date"].strftime("%Y-%m-%d"),
                    "event_date": check_date.strftime("%Y-%m-%d"),
                    "offset": offset,
                    "event": f"Стационарный {'+'.join(station_planets)}",
                    "price": row["price"],
                    "pivot_type": row["type"],
                })

        # Проверяем затмение ±3 дня (не ±7 как раньше)
        for ed in ECLIPSE_DATES:
            diff_days = abs((pivot_date - ed).days)
            if diff_days <= 3:
                etype = next(e[1] for e in ECLIPSES if datetime.strptime(e[0], "%Y-%m-%d") == ed)
                events_near_pivots.append({
                    "pivot_date": row["date"].strftime("%Y-%m-%d"),
                    "event_date": ed.strftime("%Y-%m-%d"),
                    "offset": (ed - pivot_date).days,
                    "event": f"Затмение ({etype})",
                    "price": row["price"],
                    "pivot_type": row["type"],
                })

    if events_near_pivots:
        edf = pd.DataFrame(events_near_pivots)
        print(f"\n  Найдено {len(edf)} астро-событий в ±3 днях от разворотов:")
        print(f"  {'Разворот':<12} {'Событие':<12} {'Смещ.':>6} {'Тип события':<25} {'Цена':>10} {'Тип разворота'}")
        for _, e in edf.iterrows():
            print(f"  {e['pivot_date']:<12} {e['event_date']:<12} {e['offset']:>+4}д  "
                  f"{e['event']:<25} ${e['price']:>9,.0f} {e['pivot_type']}")

        # Статистика
        unique_pivots_with_events = edf["pivot_date"].nunique()
        print(f"\n  Разворотов с астро-событием ±3д: {unique_pivots_with_events}/{len(pivots)} "
              f"({unique_pivots_with_events/len(pivots)*100:.1f}%)")


# ============================================================
# АНАЛИЗ 5: ПОВТОРЯЮЩИЕСЯ АСТРО-СИГНАТУРЫ
# ============================================================

def analyze_signatures(pdf):
    """Ищем повторяющиеся комбинации условий при разворотах."""
    print("\n\n" + "=" * 90)
    print("5. ПОВТОРЯЮЩИЕСЯ АСТРО-СИГНАТУРЫ")
    print("=" * 90)

    # Создаём сигнатуру для каждого разворота
    signatures = []
    for _, row in pdf.iterrows():
        sig_parts = []
        sig_parts.append(row["moon_quarter"])
        sig_parts.append(f"Луна-{row['moon_sign']}")
        if row["mercury_retro"]:
            sig_parts.append("Hg-retro")
        if row["near_eclipse"]:
            sig_parts.append("Eclipse")
        if row["any_station"]:
            sig_parts.append("Station")
        if row["tension_count"] >= 3:
            sig_parts.append("HiTension")
        if row["retro_count"] >= 2:
            sig_parts.append("ManyRetro")

        signatures.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "price": row["price"],
            "type": row["pivot_type"],
            "signature": " | ".join(sig_parts),
            "sig_key": frozenset(sig_parts),
        })

    sig_df = pd.DataFrame(signatures)

    # Повторяющиеся сигнатуры (≥2 разворота с одинаковым набором)
    sig_counts = Counter(sig_df["signature"])
    repeated = {k: v for k, v in sig_counts.items() if v >= 2}

    if repeated:
        print(f"\n  Сигнатуры встречающиеся ≥2 раз:")
        for sig, count in sorted(repeated.items(), key=lambda x: -x[1]):
            matches = sig_df[sig_df["signature"] == sig]
            types_count = Counter(matches["type"])
            type_str = ", ".join(f"{t}:{c}" for t, c in types_count.items())
            print(f"\n  [{count}x] {sig}")
            for _, m in matches.iterrows():
                print(f"       {m['date']}  ${m['price']:>9,.0f}  {m['type']}")
    else:
        print("  Точных повторений не найдено.")

    # Упрощённые сигнатуры (только фаза + ключевые факторы)
    print(f"\n\n  --- Упрощённые сигнатуры (фаза + 1 фактор) ---")
    simple_sigs = []
    for _, row in pdf.iterrows():
        base = row["moon_quarter"]
        factors = []
        if row["mercury_retro"]: factors.append("Hg-retro")
        if row["near_eclipse"]: factors.append("Eclipse")
        if row["any_station"]: factors.append("Station")
        if row["tension_count"] >= 3: factors.append("HiTension")
        if row["retro_count"] >= 2: factors.append("ManyRetro")

        for f in factors:
            simple_sigs.append(f"{base} + {f}")
        if not factors:
            simple_sigs.append(f"{base} (чисто)")

    simple_counts = Counter(simple_sigs)
    print(f"\n  {'Сигнатура':<35} {'Кол-во':>8}")
    for sig, count in simple_counts.most_common(20):
        bar = "█" * count
        print(f"  {sig:<35} {count:>5}  {bar}")


# ============================================================
# АНАЛИЗ 6: MAJOR РАЗВОРОТЫ (ТОЛЬКО КРУПНЫЕ)
# ============================================================

def analyze_major_only(pdf):
    """Детальный анализ только крупных разворотов."""
    print("\n\n" + "=" * 90)
    print("6. ТОЛЬКО MAJOR РАЗВОРОТЫ — ДЕТАЛЬНЫЙ ПРОФИЛЬ")
    print("=" * 90)

    major = pdf[pdf["is_major"]]
    major_highs = major[major["is_high"]]
    major_lows = major[~major["is_high"]]

    print(f"\n  Major разворотов: {len(major)} (пики: {len(major_highs)}, дно: {len(major_lows)})")

    # Частоты
    for label, subset in [("MAJOR ПИКИ", major_highs), ("MAJOR ДНО", major_lows)]:
        print(f"\n  --- {label} ({len(subset)} точек) ---")
        if len(subset) == 0:
            continue

        q_counts = Counter(subset["moon_quarter"])
        sign_counts = Counter(subset["moon_sign"])
        sun_counts = Counter(subset["sun_sign"])

        print(f"  Фазы Луны: {dict(q_counts)}")
        print(f"  Знаки Луны топ-3: {sign_counts.most_common(3)}")
        print(f"  Знаки Солнца топ-3: {sun_counts.most_common(3)}")
        print(f"  Mercury retro: {subset['mercury_retro'].sum()}/{len(subset)}")
        print(f"  Стационарность: {subset['any_station'].sum()}/{len(subset)}")
        print(f"  Eclipse ±7д: {subset['near_eclipse'].sum()}/{len(subset)}")
        print(f"  Ср. tension: {subset['tension_count'].mean():.1f}, harmony: {subset['harmony_count'].mean():.1f}")
        print(f"  Ср. ретро планет: {subset['retro_count'].mean():.1f}")


# ============================================================
# АНАЛИЗ 7: ЛУННЫЙ ДЕНЬ
# ============================================================

def analyze_lunar_days(pdf, bdf):
    """Анализ по лунным дням."""
    print("\n\n" + "=" * 90)
    print("7. ЛУННЫЕ ДНИ ПРИ РАЗВОРОТАХ")
    print("=" * 90)

    pivot_days = Counter(pdf["lunar_day"])
    base_days = Counter(bdf["lunar_day"])

    all_days_list = sorted(set(list(pivot_days.keys()) + list(base_days.keys())))

    # Collect p-values for all lunar days with enough data
    lunar_records = []
    for day in all_days_list:
        p_cnt = pivot_days.get(day, 0)
        b_rate = base_days.get(day, 0) / len(bdf)
        b_pct = b_rate * 100
        p_pct = p_cnt / len(pdf) * 100
        ratio = p_pct / max(b_pct, 0.1)

        if p_cnt >= 2 and b_rate > 0:
            p_val = stats.binomtest(p_cnt, len(pdf), b_rate).pvalue
        else:
            p_val = 1.0

        lunar_records.append({"day": day, "p_cnt": p_cnt, "p_pct": p_pct,
                              "b_pct": b_pct, "ratio": ratio, "p_value": p_val})

    apply_bh_correction(lunar_records)

    print(f"\n  {'Лунный день':>12} {'Развороты':>10} {'Base%':>8} {'Ratio':>8} {'p-value':>10} {'q-value':>10}")

    hot_days = []
    for rec in lunar_records:
        day, p_cnt, p_pct, b_pct, ratio = rec["day"], rec["p_cnt"], rec["p_pct"], rec["b_pct"], rec["ratio"]
        q_val = rec.get("q_value", 1.0)

        if p_cnt >= 3 and ratio > 1.5:
            hot_days.append((day, p_cnt, p_pct, b_pct, ratio, q_val))
            marker = " <<<"
        else:
            marker = ""

        if p_cnt >= 2:
            sig = " *" if q_val < 0.05 else ""
            print(f"  {day:>12} {p_cnt:>5} ({p_pct:>4.1f}%) {b_pct:>6.1f}% {ratio:>7.2f}x {rec['p_value']:>9.4f} {q_val:>9.4f}{sig}{marker}")

    if hot_days:
        print(f"\n  'Горячие' лунные дни (≥3 разворота, ratio > 1.5x):")
        for day, cnt, p_pct, b_pct, ratio, q_val in hot_days:
            sig = " (BH significant)" if q_val < 0.05 else ""
            print(f"    День {day}: {cnt} разворотов ({ratio:.1f}x от нормы) q={q_val:.4f}{sig}")


# ============================================================
# ВИЗУАЛИЗАЦИЯ
# ============================================================

def plot_deep_results(pdf, bdf, combo_results):
    fig, axes = plt.subplots(2, 3, figsize=(24, 14))

    highs = pdf[pdf["is_high"]]
    lows = pdf[~pdf["is_high"]]

    # 1. Tension vs Harmony при пиках и дно
    ax = axes[0, 0]
    ax.scatter(highs["tension_count"], highs["harmony_count"], c="red", alpha=0.6, s=60, label="Пики", edgecolors="black", linewidths=0.3)
    ax.scatter(lows["tension_count"], lows["harmony_count"], c="green", alpha=0.6, s=60, label="Дно", edgecolors="black", linewidths=0.3)
    ax.set_xlabel("Напряжённые аспекты (квадратуры + оппозиции)")
    ax.set_ylabel("Гармоничные аспекты (трины + секстили)")
    ax.set_title("Напряжение vs Гармония при разворотах", fontweight="bold")
    ax.legend()
    ax.grid(alpha=0.3)

    # 2. Кол-во ретроградных планет
    ax = axes[0, 1]
    retro_vals = sorted(pdf["retro_count"].unique())
    p_pcts = [len(pdf[pdf["retro_count"] == v]) / len(pdf) * 100 for v in retro_vals]
    b_pcts = [len(bdf[bdf["retro_count"] == v]) / len(bdf) * 100 for v in retro_vals]
    w = 0.35
    x = range(len(retro_vals))
    ax.bar([i - w/2 for i in x], p_pcts, w, label="Развороты", color="#FF6B6B", edgecolor="black", linewidth=0.5)
    ax.bar([i + w/2 for i in x], b_pcts, w, label="Baseline", color="#4ECDC4", edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(retro_vals)
    ax.set_xlabel("Кол-во ретроградных планет")
    ax.set_ylabel("%")
    ax.set_title("Ретроградные планеты при разворотах", fontweight="bold")
    ax.legend()

    # 3. Лунный день
    ax = axes[0, 2]
    days = range(1, 31)
    p_day = Counter(pdf["lunar_day"])
    b_day = Counter(bdf["lunar_day"])
    p_vals = [p_day.get(d, 0) / len(pdf) * 100 for d in days]
    b_vals = [b_day.get(d, 0) / len(bdf) * 100 for d in days]
    ax.bar(days, p_vals, color="#FF6B6B", alpha=0.7, label="Развороты")
    ax.plot(days, b_vals, "k--", linewidth=1, label="Baseline")
    ax.set_xlabel("Лунный день")
    ax.set_ylabel("%")
    ax.set_title("Лунные дни при разворотах", fontweight="bold")
    ax.legend()

    # 4. Пики vs Дно по знакам Луны
    ax = axes[1, 0]
    h_signs = Counter(highs["moon_sign"])
    l_signs = Counter(lows["moon_sign"])
    diffs = [(h_signs.get(s, 0) / max(len(highs), 1) - l_signs.get(s, 0) / max(len(lows), 1)) * 100 for s in ZODIAC_SIGNS]
    colors = ["#FF6B6B" if d > 0 else "#4ECDC4" for d in diffs]
    ax.barh(ZODIAC_SIGNS, diffs, color=colors, edgecolor="black", linewidth=0.5)
    ax.axvline(x=0, color="gray", linewidth=0.5)
    ax.set_xlabel("Разница (Пики% - Дно%)")
    ax.set_title("Знаки Луны: перекос пики vs дно", fontweight="bold")

    # 5. Топ комбинации
    ax = axes[1, 1]
    if combo_results:
        top_combos = combo_results[:10]
        names = [r["combo"][:30] for r in top_combos]
        ratios = [r["ratio"] for r in top_combos]
        q_vals = [r.get("q_value", 1.0) for r in top_combos]
        colors = ["#4CAF50" if q < 0.05 else "#FFC107" if q < 0.1 else "#F44336" for q in q_vals]
        ax.barh(range(len(names)), ratios, color=colors, edgecolor="black", linewidth=0.5)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=8)
        ax.axvline(x=1.0, color="gray", linestyle="--", linewidth=0.5)
        ax.set_xlabel("Ratio (развороты / baseline)")
        ax.set_title("Топ-10 комбинаций факторов (цвет = FDR)", fontweight="bold")

    # 6. Стационарность
    ax = axes[1, 2]
    station_data = {}
    for planet, col in [("Hg", "mercury_station"), ("Ve", "venus_station"),
                        ("Ma", "mars_station"), ("Ju", "jupiter_station"), ("Sa", "saturn_station")]:
        station_data[planet] = {
            "pivot": pdf[col].mean() * 100,
            "base": bdf[col].mean() * 100,
        }
    planets_l = list(station_data.keys())
    x = range(len(planets_l))
    p_s = [station_data[p]["pivot"] for p in planets_l]
    b_s = [station_data[p]["base"] for p in planets_l]
    ax.bar([i - 0.2 for i in x], p_s, 0.4, label="При разворотах", color="#FF6B6B", edgecolor="black", linewidth=0.5)
    ax.bar([i + 0.2 for i in x], b_s, 0.4, label="Baseline", color="#4ECDC4", edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(planets_l)
    ax.set_ylabel("%")
    ax.set_title("Стационарные планеты при разворотах", fontweight="bold")
    ax.legend()

    plt.suptitle("BTC x Астрология — Глубокий анализ корреляций (2020-2026)", fontsize=16, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig("astro_deep_results.png", dpi=150, bbox_inches="tight")
    print("\nГрафик: astro_deep_results.png")
    plt.close()


# ============================================================
# ИТОГОВЫЙ ВЕРДИКТ
# ============================================================

def print_verdict(pdf, bdf, combo_results):
    print("\n\n" + "=" * 90)
    print("ИТОГОВЫЕ НАХОДКИ — ЧТО РЕАЛЬНО КОРРЕЛИРУЕТ")
    print("=" * 90)

    findings = []

    # Стационарные планеты
    station_pct = pdf["any_station"].mean() * 100
    station_base = bdf["any_station"].mean() * 100
    if station_pct > 0:
        p = stats.binomtest(int(pdf["any_station"].sum()), len(pdf), bdf["any_station"].mean()).pvalue
        if p < 0.1:
            findings.append(("Стационарные планеты", station_pct, station_base, p))

    # Комбинации
    for r in combo_results:
        if r.get("q_value", 1.0) < 0.05:
            findings.append((r["combo"], r["pivot_pct"], r["base_pct"], r.get("q_value", r["p_value"])))

    # Лунные дни
    for day in range(1, 31):
        p_cnt = (pdf["lunar_day"] == day).sum()
        b_rate = (bdf["lunar_day"] == day).mean()
        if p_cnt >= 4 and b_rate > 0:
            p = stats.binomtest(p_cnt, len(pdf), b_rate).pvalue
            if p < 0.05:
                findings.append((f"Лунный день {day}", p_cnt / len(pdf) * 100, b_rate * 100, p))

    if findings:
        findings_records = [{"name": name, "pct": pct, "base": base, "p_value": p}
                            for name, pct, base, p in findings]
        apply_bh_correction(findings_records)
        findings_records.sort(key=lambda x: x["q_value"])

        print(f"\n  {'Фактор':<40} {'При разв.%':>10} {'Base%':>8} {'p-value':>10} {'q-value':>10}")
        print("  " + "-" * 82)
        for rec in findings_records:
            sig = "**" if rec["q_value"] < 0.01 else ("*" if rec["q_value"] < 0.05 else "")
            print(f"  {rec['name']:<40} {rec['pct']:>8.1f}% {rec['base']:>6.1f}% {rec['p_value']:>10.4f} {rec['q_value']:>10.4f} {sig}")

        survived = [r for r in findings_records if r["q_value"] < 0.05]
        if survived:
            print(f"\n  Выжили после BH-коррекции (q < 0.05):")
            for rec in survived:
                print(f"    {rec['name']}: p={rec['p_value']:.4f}, q={rec['q_value']:.4f}")
        else:
            print(f"\n  После BH-коррекции (q < 0.05) ничего не выжило.")
    else:
        print("\n  Значимых находок не обнаружено (p < 0.05).")

    print("\n  Напоминание: корреляция ≠ причинность.")
    print("  Даже значимые результаты могут быть случайными при множественном тестировании.")


def main():
    pivots, all_days = load_data()
    pdf, bdf = compute_astro_datasets(pivots, all_days)

    combo_results = analyze_combinations(pdf, bdf)
    analyze_highs_vs_lows(pdf, bdf)
    analyze_stations(pdf, bdf)
    analyze_window(pivots, all_days)
    analyze_signatures(pdf)
    analyze_major_only(pdf)
    analyze_lunar_days(pdf, bdf)

    plot_deep_results(pdf, bdf, combo_results)
    print_verdict(pdf, bdf, combo_results)


if __name__ == "__main__":
    main()
