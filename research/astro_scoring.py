"""
BTC Астро-скоринг: честная train/holdout-модель для разворотов.

Подход:
1. Считаем только реальные астрономические признаки через ephem.
2. Обучаем веса признаков только на train-части истории.
3. Проверяем на holdout без ручных подгонок.
4. После валидации переобучаемся на полной истории для будущего календаря.
"""

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timedelta
from functools import lru_cache

import ephem
import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

matplotlib.use("Agg")

try:
    from .log import get_logger
except ImportError:
    try:
        from log import get_logger
    except ImportError:
        import logging
        def get_logger(name: str) -> logging.Logger:
            return logging.getLogger(name)

logger = get_logger(__name__)

try:
    from .astro_shared import (
        DB_PATH,
        ECLIPSE_DATES,
        ELEMENT_MAP,
        MODALITY_MAP,
        apply_bh_correction,
        ecliptic_lon_deg,
        get_zodiac_sign,
        is_retrograde,
        is_stationary,
        today_local_date,
    )
except ImportError:
    from astro_shared import (
        DB_PATH,
        ECLIPSE_DATES,
        ELEMENT_MAP,
        MODALITY_MAP,
        apply_bh_correction,
        ecliptic_lon_deg,
        get_zodiac_sign,
        is_retrograde,
        is_stationary,
        today_local_date,
    )


RETRO_PLANETS = {
    "Меркурий": ephem.Mercury,
    "Венера": ephem.Venus,
    "Марс": ephem.Mars,
    "Юпитер": ephem.Jupiter,
    "Сатурн": ephem.Saturn,
    "Уран": ephem.Uranus,
    "Нептун": ephem.Neptune,
    "Плутон": ephem.Pluto,
}

STATION_PLANETS = {
    "Меркурий": ephem.Mercury,
    "Венера": ephem.Venus,
    "Марс": ephem.Mars,
    "Юпитер": ephem.Jupiter,
    "Сатурн": ephem.Saturn,
}

SLOW_INGRESS_PLANETS = {
    "Юпитер": ephem.Jupiter,
    "Сатурн": ephem.Saturn,
    "Уран": ephem.Uranus,
    "Нептун": ephem.Neptune,
    "Плутон": ephem.Pluto,
}

REVERSAL_FEATURE_LABELS = {
    "moon_ingress": "Ингрессия Луны",
    "moon_node_conj": "Луна у узла",
    "moon_node_square": "Луна квадрат узлам",
    "saturn_square_nodes": "Сатурн квадрат узлам",
    "sun_cancer": "Солнце в Раке (июнь-июль)",
    "sun_gemini": "Солнце в Близнецах (май-июнь)",
    "sun_cardinal": "Солнце в кардинальном знаке",
}

CONTINUOUS_REVERSAL_FEATURE_LABELS = {
    "log_days_to_eclipse": "Дни до затмения (log)",
    "station_strength": "Сила станции",
    "moon_age_sin": "Лунный цикл sin",
    "moon_age_cos": "Лунный цикл cos",
}

DIRECTION_FEATURE_LABELS = {
    "moon_ingress": "Ингрессия Луны",
    "any_station": "Стационарная планета",
    "eclipse_3d": "Затмение ±3д",
    "eclipse_7d": "Затмение ±7д",
    "moon_water": "Луна в Воде",
    "moon_earth": "Луна в Земле",
    "moon_cardinal": "Луна в кардинальном знаке",
    "moon_node_conj": "Луна у узла",
    "moon_node_square": "Луна квадрат узлам",
    "saturn_square_nodes": "Сатурн квадрат узлам",
    "sun_cancer": "Солнце в Раке (июнь-июль)",
    "sun_gemini": "Солнце в Близнецах (май-июнь)",
    "sun_cardinal": "Солнце в кардинальном знаке",
    "sun_libra": "Солнце в Весах (сент-окт)",
}


@lru_cache(maxsize=None)
def _planet_lon_for_ordinal(planet_name: str, ordinal: int) -> float:
    planet_class = RETRO_PLANETS[planet_name]
    return _get_ecliptic_lon(planet_class(ephem.Date(datetime.fromordinal(ordinal))))


@lru_cache(maxsize=None)
def _planet_speed_for_ordinal(planet_name: str, ordinal: int) -> float:
    lon_now = _planet_lon_for_ordinal(planet_name, ordinal)
    lon_prev = _planet_lon_for_ordinal(planet_name, ordinal - 1)
    diff = lon_now - lon_prev
    if diff > 180:
        diff -= 360
    elif diff < -180:
        diff += 360
    return diff


def _angular_distance_deg(lon_a: float, lon_b: float) -> float:
    diff = abs(lon_a - lon_b)
    return diff if diff <= 180 else 360 - diff


# _is_retrograde, _is_stationary, _get_ecliptic_lon → astro_shared
_get_ecliptic_lon = ecliptic_lon_deg
_is_retrograde = is_retrograde
_is_stationary = is_stationary


def _get_lunar_node(d):
    jd = ephem.julian_date(d)
    t = (jd - 2451545.0) / 36525.0
    omega = 125.04452 - 1934.136261 * t + 0.0020708 * t**2 + t**3 / 450000
    omega = omega % 360
    return omega if omega >= 0 else omega + 360


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
    prev_new = ephem.previous_new_moon(d)
    next_new = ephem.next_new_moon(d)
    prev_full = ephem.previous_full_moon(d)
    next_full = ephem.next_full_moon(d)
    dist_new = min(abs(d - prev_new), abs(next_new - d))
    dist_full = min(abs(d - prev_full), abs(next_full - d))
    return float(dist_new), float(dist_full)


def _quarter_distance(d):
    prev_fq = ephem.previous_first_quarter_moon(d)
    next_fq = ephem.next_first_quarter_moon(d)
    prev_lq = ephem.previous_last_quarter_moon(d)
    next_lq = ephem.next_last_quarter_moon(d)
    dist_fq = min(abs(d - prev_fq), abs(next_fq - d))
    dist_lq = min(abs(d - prev_lq), abs(next_lq - d))
    return float(min(dist_fq, dist_lq))


def _classify_quarter(d):
    prev_new = ephem.previous_new_moon(d)
    next_new = ephem.next_new_moon(d)
    cycle_len = next_new - prev_new
    position = (d - prev_new) / cycle_len
    if position < 0.125 or position >= 0.875:
        return "Новолуние"
    if position < 0.375:
        return "Растущая"
    if position < 0.625:
        return "Полнолуние"
    return "Убывающая"


def _station_event_strength(planet_name: str, ordinal: int) -> float:
    if planet_name not in STATION_PLANETS:
        return 0.0

    planet_class = STATION_PLANETS[planet_name]
    check_date = ephem.Date(datetime.fromordinal(ordinal))
    if not _is_stationary(planet_class, check_date, orb_days=1):
        return 0.0

    speed_before = abs(_planet_speed_for_ordinal(planet_name, ordinal))
    speed_after = abs(_planet_speed_for_ordinal(planet_name, ordinal + 1))
    local_scale = max(speed_before, speed_after, 1e-6)
    slowness = 1.0 - min(speed_before, speed_after) / local_scale
    return max(0.0, min(1.0, slowness))


def _station_strength(date, window_days=6):
    ordinal = date.date().toordinal()
    best = 0.0
    for planet_name in STATION_PLANETS:
        for offset in range(-window_days, window_days + 1):
            event_strength = _station_event_strength(planet_name, ordinal + offset)
            if event_strength <= 0:
                continue
            proximity = math.exp(-abs(offset) / 3.0)
            best = max(best, event_strength * proximity)
    return round(best, 4)


def extract_astro_profile(date, eclipse_dates=None):
    """Астро-профиль для даты. eclipse_dates ограничивает список затмений (фикс data leakage)."""
    if eclipse_dates is None:
        eclipse_dates = ECLIPSE_DATES
    d = ephem.Date(date)
    d_prev = ephem.Date(date - timedelta(days=1))
    moon = ephem.Moon(d)

    moon_lon = _get_ecliptic_lon(moon)
    moon_sign = get_zodiac_sign(moon_lon)
    moon_element = ELEMENT_MAP[moon_sign]
    moon_modality = MODALITY_MAP[moon_sign]

    dist_new, dist_full = _days_to_nearest_phase(d)
    dist_quarter = _quarter_distance(d)
    quarter = _classify_quarter(d)
    prev_new = ephem.previous_new_moon(d)
    next_new = ephem.next_new_moon(d)
    cycle_len = next_new - prev_new
    moon_cycle_pos = float((d - prev_new) / cycle_len)
    moon_cycle_angle = 2 * math.pi * moon_cycle_pos

    if eclipse_dates:
        min_eclipse = min(abs((date - ed).days) for ed in eclipse_dates)
    else:
        min_eclipse = 999
    moon_ingress, new_sign = _detect_ingress(ephem.Moon, d, window_hours=6)
    station_strength = _station_strength(date)

    retro_planets = [name for name, cls in RETRO_PLANETS.items() if _is_retrograde(cls, d, d_prev)]
    station_planets = [name for name, cls in STATION_PLANETS.items() if _is_stationary(cls, d)]

    slow_ingresses = []
    for name, cls in SLOW_INGRESS_PLANETS.items():
        is_ingress, ingress_sign = _detect_ingress(cls, d, window_hours=24)
        if is_ingress:
            slow_ingresses.append(f"{name} -> {ingress_sign}")

    rahu_lon = _get_lunar_node(d)
    ketu_lon = (rahu_lon + 180) % 360
    moon_rahu = _angular_distance_deg(moon_lon, rahu_lon)
    moon_ketu = _angular_distance_deg(moon_lon, ketu_lon)
    saturn_lon = _get_ecliptic_lon(ephem.Saturn(d))
    saturn_rahu = _angular_distance_deg(saturn_lon, rahu_lon)

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
    for i, name_i in enumerate(bodies):
        for name_j in list(bodies.keys())[i + 1:]:
            diff = abs(bodies[name_i] - bodies[name_j])
            diff = diff if diff <= 180 else 360 - diff
            if abs(diff - 90) <= 8 or abs(diff - 180) <= 8:
                tension += 1
            elif abs(diff - 120) <= 8 or abs(diff - 60) <= 6:
                harmony += 1

    sun_lon = bodies["Солнце"]
    sun_sign = get_zodiac_sign(sun_lon)
    sun_element = ELEMENT_MAP[sun_sign]
    sun_modality = MODALITY_MAP[sun_sign]

    features = {
        "new_1d": dist_new <= 1,
        "new_2d": 1 < dist_new <= 2,
        "full_1d": dist_full <= 1,
        "full_2d": 1 < dist_full <= 2,
        "quarter_1d": dist_quarter <= 1,
        "eclipse_3d": min_eclipse <= 3,
        "eclipse_7d": 3 < min_eclipse <= 7,
        "moon_ingress": moon_ingress,
        "mars_retro": "Марс" in retro_planets,
        "jupiter_retro": "Юпитер" in retro_planets,
        "mars_jupiter_retro": "Марс" in retro_planets and "Юпитер" in retro_planets,
        "retro_2plus": len(retro_planets) >= 2,
        "retro_4plus": len(retro_planets) >= 4,
        "any_station": bool(station_planets),
        "slow_ingress": bool(slow_ingresses),
        "moon_node_conj": moon_rahu <= 10 or moon_ketu <= 10,
        "moon_node_square": abs(moon_rahu - 90) <= 8,
        "saturn_square_nodes": abs(saturn_rahu - 90) <= 8,
        "tension_3plus": tension >= 3,
        "moon_water": moon_element == "Вода",
        "moon_earth": moon_element == "Земля",
        "moon_mutable": moon_modality == "Мутабельный",
        "moon_cardinal": moon_modality == "Кардинальный",
        "sun_cancer": sun_sign == "Рак",
        "sun_gemini": sun_sign == "Близнецы",
        "sun_libra": sun_sign == "Весы",
        "sun_cardinal": sun_modality == "Кардинальный",
        "days_to_eclipse": float(min_eclipse),
        "log_days_to_eclipse": math.log1p(float(min_eclipse)),
        "station_strength": station_strength,
        "moon_age_sin": math.sin(moon_cycle_angle),
        "moon_age_cos": math.cos(moon_cycle_angle),
    }

    return {
        "date": date,
        "score": 0.0,
        "direction": 0.0,
        "details": [],
        "moon_sign": moon_sign,
        "moon_element": moon_element,
        "sun_sign": sun_sign,
        "sun_element": sun_element,
        "quarter": quarter,
        "retro_planets": retro_planets,
        "station_planets": station_planets,
        "eclipse_days": min_eclipse,
        "station_strength": station_strength,
        "moon_ingress": moon_ingress,
        "tension": tension,
        "harmony": harmony,
        "moon_ingress_sign": new_sign,
        "slow_ingresses": slow_ingresses,
        **features,
    }


def load_historical_data():
    conn = sqlite3.connect(DB_PATH)
    pivots = pd.read_sql(
        """
        SELECT date, price, type, pct_change
        FROM btc_pivots
        ORDER BY date
        """,
        conn,
    )
    all_days = pd.read_sql(
        """
        SELECT date, close
        FROM btc_daily
        ORDER BY date
        """,
        conn,
    )
    conn.close()
    pivots["date"] = pd.to_datetime(pivots["date"])
    all_days["date"] = pd.to_datetime(all_days["date"])
    return pivots, all_days


def build_history_features(all_days: pd.DataFrame, eclipse_cutoff: datetime | None = None) -> pd.DataFrame:
    """Считает астро для всей истории. eclipse_cutoff ограничивает список затмений."""
    print("\nПодсчёт астропризнаков для всей истории...")
    if eclipse_cutoff is not None:
        allowed_eclipses = [ed for ed in ECLIPSE_DATES if ed <= eclipse_cutoff]
    else:
        allowed_eclipses = ECLIPSE_DATES
    records = []
    for idx, row in all_days.iterrows():
        record = extract_astro_profile(row["date"].to_pydatetime(), eclipse_dates=allowed_eclipses)
        record["close"] = row["close"]
        records.append(record)
        if (idx + 1) % 250 == 0:
            print(f"  {idx + 1}/{len(all_days)} дней...")
    return pd.DataFrame(records).sort_values("date").reset_index(drop=True)


def annotate_pivots(history_df: pd.DataFrame, pivots: pd.DataFrame) -> pd.DataFrame:
    pivot_meta = pivots.copy()
    pivot_meta["is_pivot"] = True
    pivot_meta["is_high"] = pivot_meta["type"].str.contains("high")
    merged = history_df.merge(
        pivot_meta[["date", "price", "type", "pct_change", "is_pivot", "is_high"]],
        on="date",
        how="left",
        validate="one_to_one",
    )
    merged["is_pivot"] = merged["is_pivot"].fillna(False).astype(bool)
    merged["is_high"] = merged["is_high"].fillna(False).astype(bool)
    return merged


def assign_sample_split(history_df: pd.DataFrame, test_ratio: float = 0.20) -> tuple[pd.DataFrame, pd.Timestamp]:
    history_df = history_df.sort_values("date").reset_index(drop=True).copy()
    split_idx = max(1, min(int(len(history_df) * (1 - test_ratio)), len(history_df) - 1))
    split_start = history_df.loc[split_idx, "date"]
    history_df["sample_split"] = np.where(history_df["date"] >= split_start, "test", "train")
    return history_df, split_start


try:
    from .config import WEIGHT_SHRINKAGE_FACTOR
except ImportError:
    try:
        from config import WEIGHT_SHRINKAGE_FACTOR
    except ImportError:
        WEIGHT_SHRINKAGE_FACTOR = 0.85


def _shrunken_weight(lift: float, p_value: float, scale: float, p_cap: float) -> float:
    lift = max(lift, 1e-6)
    strength = abs(math.log2(lift))
    shrink = max(0.0, min(1.0, (p_cap - p_value) / p_cap))
    return round(min(scale, strength * scale * shrink) * WEIGHT_SHRINKAGE_FACTOR, 2)


def _continuous_weight(effect_size: float, p_value: float, scale: float = 0.75, p_cap: float = 0.25) -> float:
    shrink = max(0.0, min(1.0, (p_cap - p_value) / p_cap))
    raw = effect_size * scale * shrink * WEIGHT_SHRINKAGE_FACTOR
    return round(max(-1.0, min(1.0, raw)), 2)


def fit_reversal_model(train_df: pd.DataFrame) -> dict:
    train_df = train_df.copy()
    train_df["is_pivot"] = train_df["is_pivot"].astype(bool)
    pivots = train_df[train_df["is_pivot"]]
    non_pivots = train_df[~train_df["is_pivot"]]

    # --- Шаг 1: собираем все p-values для binary и continuous ---
    binary_candidates = []
    diagnostics = []

    for col, label in REVERSAL_FEATURE_LABELS.items():
        pivot_count = int(pivots[col].sum())
        base_rate = float(non_pivots[col].mean())
        if pivot_count < 4 or base_rate <= 0 or base_rate >= 1:
            continue
        p_value = stats.binomtest(pivot_count, len(pivots), base_rate).pvalue
        pivot_pct = pivot_count / len(pivots)
        lift = pivot_pct / base_rate
        binary_candidates.append({
            "col": col, "label": label, "p_value": p_value,
            "pivot_pct": pivot_pct, "base_rate": base_rate, "lift": lift,
        })
        diagnostics.append((label, pivot_pct * 100, base_rate * 100, p_value))

    continuous_candidates = []
    continuous_diagnostics = []

    for col, label in CONTINUOUS_REVERSAL_FEATURE_LABELS.items():
        pivot_values = pivots[col].astype(float)
        base_values = non_pivots[col].astype(float)
        base_std = float(base_values.std(ddof=0))
        if base_std <= 1e-9:
            continue
        t_stat, p_value = stats.ttest_ind(pivot_values, base_values, equal_var=False)
        effect_size = (float(pivot_values.mean()) - float(base_values.mean())) / base_std
        continuous_candidates.append({
            "col": col, "label": label, "p_value": float(p_value),
            "effect_size": float(effect_size),
            "base_mean": float(base_values.mean()), "base_std": base_std,
        })
        continuous_diagnostics.append((label, float(pivot_values.mean()), float(base_values.mean()), float(p_value), float(effect_size)))

    # --- Шаг 2: BH-коррекция по ВСЕМ тестам совместно ---
    all_records = []
    for item in binary_candidates:
        all_records.append({"source": "binary", "col": item["col"], "p_value": item["p_value"]})
    for item in continuous_candidates:
        all_records.append({"source": "continuous", "col": item["col"], "p_value": item["p_value"]})

    apply_bh_correction(all_records)
    q_map = {rec["col"]: rec["q_value"] for rec in all_records}

    # --- Шаг 3: отбираем по q_value < 0.25 (стандартный exploratory FDR) ---
    FDR_THRESHOLD = 0.25
    weights = {}
    for item in binary_candidates:
        q_value = q_map.get(item["col"], 1.0)
        if q_value >= FDR_THRESHOLD:
            continue
        weight = _shrunken_weight(item["lift"], item["p_value"], scale=3.0, p_cap=FDR_THRESHOLD)
        if item["pivot_pct"] < item["base_rate"]:
            weight *= -1
        if abs(weight) >= 0.15:
            weights[item["col"]] = weight

    continuous_weights = {}
    for item in continuous_candidates:
        q_value = q_map.get(item["col"], 1.0)
        if q_value >= FDR_THRESHOLD:
            continue
        weight = _continuous_weight(item["effect_size"], item["p_value"], p_cap=FDR_THRESHOLD)
        if abs(weight) >= 0.05:
            continuous_weights[item["col"]] = {
                "weight": weight,
                "mean": item["base_mean"],
                "std": item["base_std"],
            }

    return {
        "weights": weights,
        "diagnostics": diagnostics,
        "continuous_weights": continuous_weights,
        "continuous_diagnostics": continuous_diagnostics,
    }


def fit_direction_model(train_df: pd.DataFrame) -> dict:
    train_df = train_df.copy()
    train_df["is_pivot"] = train_df["is_pivot"].astype(bool)
    train_df["is_high"] = train_df["is_high"].astype(bool)
    pivots = train_df[train_df["is_pivot"]]
    highs = pivots[pivots["is_high"]]
    lows = pivots[~pivots["is_high"]]

    # --- Шаг 1: собираем все p-values ---
    candidates = []
    diagnostics = []

    for col, label in DIRECTION_FEATURE_LABELS.items():
        high_count = int(highs[col].sum())
        low_count = int(lows[col].sum())
        total_active = high_count + low_count
        if total_active < 4:
            continue
        table = np.array([[high_count, len(highs) - high_count], [low_count, len(lows) - low_count]])
        _, p_value = stats.fisher_exact(table)
        high_rate = high_count / max(len(highs), 1)
        low_rate = low_count / max(len(lows), 1)
        lift = (high_rate + 1e-6) / (low_rate + 1e-6)
        candidates.append({
            "col": col, "label": label, "p_value": float(p_value),
            "high_rate": high_rate, "low_rate": low_rate, "lift": lift,
        })
        diagnostics.append((label, high_rate * 100, low_rate * 100, p_value))

    # --- Шаг 2: BH-коррекция ---
    fdr_records = [{"col": c["col"], "p_value": c["p_value"]} for c in candidates]
    apply_bh_correction(fdr_records)
    q_map = {rec["col"]: rec["q_value"] for rec in fdr_records}

    # --- Шаг 3: отбор по q_value < 0.25 (стандартный exploratory FDR) ---
    FDR_THRESHOLD = 0.25
    weights = {}
    for item in candidates:
        q_value = q_map.get(item["col"], 1.0)
        if q_value >= FDR_THRESHOLD:
            continue
        weight = _shrunken_weight(item["lift"], item["p_value"], scale=2.0, p_cap=FDR_THRESHOLD)
        if item["high_rate"] < item["low_rate"]:
            weight *= -1
        if abs(weight) >= 0.10:
            weights[item["col"]] = weight

    return {
        "weights": weights,
        "diagnostics": diagnostics,
    }


def fit_scoring_model(train_df: pd.DataFrame) -> dict:
    return {
        "reversal_model": fit_reversal_model(train_df),
        "direction_model": fit_direction_model(train_df),
    }


def refit_model(full_df: pd.DataFrame, train_model: dict) -> dict:
    """Переоценивает веса на полных данных, используя признаки отобранные на train.

    Отбор признаков (BH-коррекция) делается ТОЛЬКО на train.
    Full model просто re-fit весов для тех же признаков — повторный BH не нужен.
    """
    full_df = full_df.copy()
    full_df["is_pivot"] = full_df["is_pivot"].astype(bool)
    full_df["is_high"] = full_df["is_high"].astype(bool)
    pivots = full_df[full_df["is_pivot"]]
    non_pivots = full_df[~full_df["is_pivot"]]

    FDR_THRESHOLD = 0.25

    # --- Reversal: refit только для отобранных на train признаков ---
    selected_binary = set(train_model["reversal_model"]["weights"].keys())
    selected_continuous = set(train_model["reversal_model"]["continuous_weights"].keys())

    weights = {}
    for col in selected_binary:
        label = REVERSAL_FEATURE_LABELS.get(col, col)
        pivot_count = int(pivots[col].sum())
        base_rate = float(non_pivots[col].mean())
        if pivot_count < 2 or base_rate <= 0 or base_rate >= 1:
            continue
        p_value = stats.binomtest(pivot_count, len(pivots), base_rate).pvalue
        pivot_pct = pivot_count / len(pivots)
        lift = pivot_pct / base_rate
        weight = _shrunken_weight(lift, p_value, scale=3.0, p_cap=FDR_THRESHOLD)
        if pivot_pct < base_rate:
            weight *= -1
        if abs(weight) >= 0.15:
            weights[col] = weight

    continuous_weights = {}
    for col in selected_continuous:
        pivot_values = pivots[col].astype(float)
        base_values = non_pivots[col].astype(float)
        base_std = float(base_values.std(ddof=0))
        if base_std <= 1e-9:
            continue
        _, p_value = stats.ttest_ind(pivot_values, base_values, equal_var=False)
        effect_size = (float(pivot_values.mean()) - float(base_values.mean())) / base_std
        weight = _continuous_weight(effect_size, float(p_value), p_cap=FDR_THRESHOLD)
        if abs(weight) >= 0.05:
            continuous_weights[col] = {
                "weight": weight,
                "mean": float(base_values.mean()),
                "std": base_std,
            }

    # --- Direction: refit отобранных на train ---
    selected_direction = set(train_model["direction_model"]["weights"].keys())
    highs = pivots[pivots["is_high"]]
    lows = pivots[~pivots["is_high"]]

    dir_weights = {}
    for col in selected_direction:
        high_count = int(highs[col].sum())
        low_count = int(lows[col].sum())
        if high_count + low_count < 2:
            continue
        table = np.array([[high_count, len(highs) - high_count], [low_count, len(lows) - low_count]])
        _, p_value = stats.fisher_exact(table)
        high_rate = high_count / max(len(highs), 1)
        low_rate = low_count / max(len(lows), 1)
        lift = (high_rate + 1e-6) / (low_rate + 1e-6)
        weight = _shrunken_weight(lift, p_value, scale=2.0, p_cap=FDR_THRESHOLD)
        if high_rate < low_rate:
            weight *= -1
        if abs(weight) >= 0.10:
            dir_weights[col] = weight

    return {
        "reversal_model": {
            "weights": weights,
            "diagnostics": train_model["reversal_model"]["diagnostics"],
            "continuous_weights": continuous_weights,
            "continuous_diagnostics": train_model["reversal_model"]["continuous_diagnostics"],
        },
        "direction_model": {
            "weights": dir_weights,
            "diagnostics": train_model["direction_model"]["diagnostics"],
        },
    }


def apply_model_to_profile(profile: dict, model: dict) -> dict:
    profile = dict(profile)
    reversal_score = 0.0
    direction_score = 0.0
    reversal_details = []
    direction_details = []

    for col, weight in model["reversal_model"]["weights"].items():
        if profile.get(col):
            reversal_score += weight
            reversal_details.append(f"{weight:+.1f}  {REVERSAL_FEATURE_LABELS[col]}")

    for col, params in model["reversal_model"]["continuous_weights"].items():
        std = max(params["std"], 1e-9)
        z_value = (float(profile.get(col, 0.0)) - params["mean"]) / std
        z_value = max(-2.0, min(2.0, z_value))
        contribution = params["weight"] * z_value
        if abs(contribution) >= 0.05:
            reversal_score += contribution
            reversal_details.append(f"{contribution:+.1f}  {CONTINUOUS_REVERSAL_FEATURE_LABELS[col]}")

    for col, weight in model["direction_model"]["weights"].items():
        if profile.get(col):
            direction_score += weight

    for col, label in DIRECTION_FEATURE_LABELS.items():
        weight = model["direction_model"]["weights"].get(col)
        if weight and profile.get(col) and abs(weight) >= 0.4:
            arrow = "↑" if weight > 0 else "↓"
            target = "пик" if weight > 0 else "дно"
            direction_details.append(f"  {arrow} {label} → скорее {target}")

    profile["reversal_score"] = round(reversal_score, 1)
    profile["direction_score"] = round(direction_score, 1)
    profile["score"] = profile["reversal_score"]
    profile["direction"] = profile["direction_score"]
    profile["reversal_details"] = reversal_details
    profile["direction_details"] = direction_details
    profile["details"] = reversal_details + direction_details
    return profile


def score_history(history_df: pd.DataFrame, model: dict) -> pd.DataFrame:
    records = []
    for _, row in history_df.iterrows():
        scored = apply_model_to_profile(row.to_dict(), model)
        records.append(scored)
    return pd.DataFrame(records)


def derive_thresholds(
    base_scores: np.ndarray,
    pivot_scores: np.ndarray | None = None,
    target_precisions: tuple[float, ...] = (3.0, 5.0, 8.0, 12.0),
) -> list[float]:
    """Precision-based пороги: для каждого target_precision% находим порог score.

    Precision = pivot_above / (pivot_above + base_above) * 100.
    Если pivot_scores не переданы — fallback на квантили base_scores.
    """
    if len(base_scores) == 0:
        return [0.5, 1.0, 1.5, 2.0]

    if pivot_scores is None or len(pivot_scores) == 0:
        raw = sorted({round(float(np.quantile(base_scores, q)), 1) for q in [0.75, 0.85, 0.90, 0.95]})
        thresholds = [v for v in raw if v > 0]
        if not thresholds:
            return [0.5, 1.0, 1.5, 2.0]
        while len(thresholds) < 4:
            thresholds.append(round(thresholds[-1] + 0.5, 1))
        return thresholds[:4]

    all_scores = np.concatenate([base_scores, pivot_scores])
    unique_thresholds = sorted(t for t in set(round(float(s), 1) for s in all_scores) if t > 0)
    if not unique_thresholds:
        return [0.5, 1.0, 1.5, 2.0]

    thresholds = []
    for target_pct in target_precisions:
        best_t = None
        for t in unique_thresholds:
            p_above = int((pivot_scores >= t).sum())
            b_above = int((base_scores >= t).sum())
            if p_above + b_above == 0:
                continue
            precision = p_above / (p_above + b_above) * 100
            if precision >= target_pct:
                best_t = t
                break
        if best_t is not None:
            thresholds.append(best_t)

    # Дедупликация и гарантия 4 порогов
    thresholds = sorted(set(thresholds))
    if not thresholds:
        return [0.5, 1.0, 1.5, 2.0]
    while len(thresholds) < 4:
        thresholds.append(round(thresholds[-1] + 0.5, 1))
    return thresholds[:4]


def print_validation_block(label: str, pdf: pd.DataFrame, base_arr: np.ndarray, thresholds: list[float]) -> dict:
    print(f"\n  --- {label} ---")
    print(f"  Разворотов: {len(pdf)}, непивотных дней: {len(base_arr)}")

    if len(pdf) == 0 or len(base_arr) == 0:
        print("  Недостаточно данных для статистики.")
        return {"direction_accuracy": 0.0, "thresholds": []}

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
    threshold_rows = []
    for threshold in thresholds:
        p_above = int((pdf["score"] >= threshold).sum())
        b_above_pct = float((base_arr >= threshold).mean() * 100)
        p_pct = p_above / len(pdf) * 100
        lift = p_pct / b_above_pct if b_above_pct > 0 else 0.0
        total_days_above = int((base_arr >= threshold).sum())
        precision = p_above / max(p_above + total_days_above, 1) * 100
        threshold_rows.append(
            {
                "threshold": threshold,
                "pivot_pct": round(p_pct, 1),
                "base_pct": round(b_above_pct, 1),
                "lift": round(lift, 2),
                "precision": round(precision, 1),
            }
        )
        print(
            f"  {threshold:>6.1f}+ {p_above:>6}/{len(pdf):>3} {p_pct:>6.1f}% "
            f"{b_above_pct:>6.1f}% {lift:>7.2f}x {precision:>8.1f}%"
        )

    pdf = pdf.copy()
    pdf["is_high"] = pdf["is_high"].astype(bool)
    highs = pdf[pdf["is_high"]]
    lows = pdf[~pdf["is_high"]]
    correct_dir = int((highs["direction"] > 0).sum() + (lows["direction"] < 0).sum())
    total_with_dir = int((highs["direction"] != 0).sum() + (lows["direction"] != 0).sum())
    direction_accuracy = correct_dir / total_with_dir * 100 if total_with_dir else 0.0

    print(f"\n  Пики ({len(highs)}): ср. reversal = {highs['score'].mean():.2f}, ср. direction = {highs['direction'].mean():.2f}")
    print(f"  Дно ({len(lows)}): ср. reversal = {lows['score'].mean():.2f}, ср. direction = {lows['direction'].mean():.2f}")
    if total_with_dir:
        print(f"  Точность направления: {correct_dir}/{total_with_dir} ({direction_accuracy:.1f}%)")

    return {
        "direction_accuracy": round(direction_accuracy, 1),
        "t_test_p": round(p_value, 4),
        "mw_p": round(p_mw, 4),
        "thresholds": threshold_rows,
    }


def print_model_summary(model: dict):
    print("\n  Обученные весы reversal-модели:")
    if model["reversal_model"]["weights"]:
        for col, weight in sorted(model["reversal_model"]["weights"].items(), key=lambda item: abs(item[1]), reverse=True):
            print(f"    {REVERSAL_FEATURE_LABELS[col]:<35} {weight:+.2f}")
    else:
        print("    Нет отобранных признаков.")

    print("\n  Обученные continuous reversal-веса:")
    if model["reversal_model"]["continuous_weights"]:
        for col, params in sorted(
            model["reversal_model"]["continuous_weights"].items(),
            key=lambda item: abs(item[1]["weight"]),
            reverse=True,
        ):
            print(f"    {CONTINUOUS_REVERSAL_FEATURE_LABELS[col]:<35} {params['weight']:+.2f}")
    else:
        print("    Нет отобранных признаков.")

    print("\n  Обученные весы direction-модели:")
    if model["direction_model"]["weights"]:
        for col, weight in sorted(model["direction_model"]["weights"].items(), key=lambda item: abs(item[1]), reverse=True):
            print(f"    {DIRECTION_FEATURE_LABELS[col]:<35} {weight:+.2f}")
    else:
        print("    Нет отобранных признаков.")


def validate_model():
    print("=" * 90)
    print("ВАЛИДАЦИЯ СКОРИНГОВОЙ МОДЕЛИ НА ИСТОРИЧЕСКИХ ДАННЫХ")
    print("=" * 90)

    pivots, all_days = load_historical_data()

    # Определяем split_date до подсчёта признаков (для eclipse leakage fix)
    split_idx = max(1, min(int(len(all_days) * 0.80), len(all_days) - 1))
    split_date = all_days.loc[split_idx, "date"].to_pydatetime()
    print(f"  Eclipse cutoff для train: {split_date.strftime('%Y-%m-%d')}")

    # Train-данные считаются только с затмениями до split_date (no leakage)
    history_df = build_history_features(all_days, eclipse_cutoff=split_date)
    history_df = annotate_pivots(history_df, pivots)
    history_df, split_start = assign_sample_split(history_df)

    train_df = history_df[history_df["sample_split"] == "train"].copy()
    train_model = fit_scoring_model(train_df)
    print_model_summary(train_model)

    scored_history = score_history(history_df, train_model)
    scored_history["close"] = history_df["close"]
    scored_history["type"] = history_df["type"]
    scored_history["price"] = history_df["price"]
    scored_history["pct_change"] = history_df["pct_change"]
    scored_history["is_pivot"] = history_df["is_pivot"].astype(bool)
    scored_history["is_high"] = history_df["is_high"].astype(bool)
    scored_history["sample_split"] = history_df["sample_split"]

    print(
        f"\nИстория: {scored_history['date'].min().strftime('%Y-%m-%d')} — "
        f"{scored_history['date'].max().strftime('%Y-%m-%d')}"
    )
    print(
        f"Holdout split: train < {split_start.strftime('%Y-%m-%d')}, "
        f"test >= {split_start.strftime('%Y-%m-%d')}"
    )

    train_pdf = scored_history[(scored_history["sample_split"] == "train") & (scored_history["is_pivot"])].copy()
    train_base = scored_history[(scored_history["sample_split"] == "train") & (~scored_history["is_pivot"])]["score"].to_numpy()
    train_pivot_scores = train_pdf["score"].to_numpy()
    thresholds = derive_thresholds(train_base, train_pivot_scores)
    print(f"\n  Precision-based пороги из train: {', '.join(f'{t:.1f}' for t in thresholds)}")

    test_pdf = scored_history[(scored_history["sample_split"] == "test") & (scored_history["is_pivot"])].copy()
    test_base = scored_history[(scored_history["sample_split"] == "test") & (~scored_history["is_pivot"])]["score"].to_numpy()

    train_metrics = print_validation_block("TRAIN", train_pdf, train_base, thresholds)
    test_metrics = print_validation_block("TEST (holdout)", test_pdf, test_base, thresholds)

    # Full model: используем ВСЕ затмения (для календаря будущего)
    full_history_df = build_history_features(all_days)
    full_history_df = annotate_pivots(full_history_df, pivots)
    full_history_df["sample_split"] = history_df["sample_split"]

    full_model = refit_model(full_history_df, train_model)
    full_scored_history = score_history(full_history_df, full_model)
    full_scored_history["close"] = full_history_df["close"]
    full_scored_history["type"] = full_history_df["type"]
    full_scored_history["price"] = full_history_df["price"]
    full_scored_history["pct_change"] = full_history_df["pct_change"]
    full_scored_history["is_pivot"] = full_history_df["is_pivot"].astype(bool)
    full_scored_history["is_high"] = full_history_df["is_high"].astype(bool)
    full_scored_history["sample_split"] = full_history_df["sample_split"]
    full_base = full_scored_history[~full_scored_history["is_pivot"]]["score"].to_numpy()
    full_pivot = full_scored_history[full_scored_history["is_pivot"]]["score"].to_numpy()
    full_thresholds = derive_thresholds(full_base, full_pivot)

    return (
        scored_history, test_pdf, test_base, test_metrics, full_model,
        thresholds, full_scored_history, full_thresholds,
        train_metrics, split_start,
    )


def generate_calendar(start_date, end_date, model, thresholds):
    print(f"\n\n{'=' * 90}")
    print(f"АСТРО-КАЛЕНДАРЬ BTC: {start_date.strftime('%Y-%m-%d')} — {end_date.strftime('%Y-%m-%d')}")
    print(f"{'=' * 90}")

    rows = []
    current = start_date
    while current <= end_date:
        profile = extract_astro_profile(current)
        scored = apply_model_to_profile(profile, model)
        rows.append(scored)
        current += timedelta(days=1)

    df = pd.DataFrame(rows)
    hot_threshold = thresholds[min(2, len(thresholds) - 1)]
    warm_threshold = thresholds[0]

    hot_zones = df[df["score"] >= hot_threshold].copy()
    if len(hot_zones) > 0:
        print(f"\n  ЗОНЫ ПОВЫШЕННОГО РИСКА РАЗВОРОТА (reversal_score ≥ {hot_threshold:.1f}):")
        print(f"  {'Дата':<12} {'Скор':>5} {'Направл.':>10} {'Луна':>15} {'Детали'}")
        print("  " + "-" * 85)
        for _, row in hot_zones.iterrows():
            dir_str = "↑ скорее пик" if row["direction"] > 0 else "↓ скорее дно" if row["direction"] < 0 else "нейтрально"
            moon_info = f"{row['quarter'][:4]} {row['moon_sign']}"
            detail_short = "; ".join(d.strip().split("  ")[-1][:40] for d in row["details"] if d.startswith(("+", "-")))
            print(
                f"  {row['date'].strftime('%Y-%m-%d'):<12} {row['score']:>5.1f} "
                f"{dir_str:>12} {moon_info:>15}  {detail_short[:50]}"
            )
    else:
        print("\n  Зон с высоким скором не найдено.")

    print(f"\n\n  КЛАСТЕРЫ (дни подряд с reversal_score ≥ {warm_threshold:.1f}):")
    cluster_days = df[df["score"] >= warm_threshold]
    if len(cluster_days) > 0:
        clusters = []
        current_cluster = []
        for _, row in cluster_days.iterrows():
            if not current_cluster or (row["date"] - current_cluster[-1]["date"]).days <= 2:
                current_cluster.append(row)
            else:
                clusters.append(current_cluster)
                current_cluster = [row]
        if current_cluster:
            clusters.append(current_cluster)

        for cluster in clusters:
            start = cluster[0]["date"]
            end = cluster[-1]["date"]
            max_score = max(c["score"] for c in cluster)
            avg_dir = np.mean([c["direction"] for c in cluster])
            dir_str = "↑ ПИК" if avg_dir > 0.4 else "↓ ДНО" if avg_dir < -0.4 else "?"
            if (end - start).days == 0:
                print(f"  {start.strftime('%Y-%m-%d'):>12}           макс={max_score:.1f}  {dir_str}")
            else:
                print(f"  {start.strftime('%Y-%m-%d')} — {end.strftime('%Y-%m-%d')}  макс={max_score:.1f}  {dir_str}")

    return df


def plot_results(pdf, base_arr, calendar_df, thresholds):
    fig, axes = plt.subplots(2, 2, figsize=(22, 14))
    hot_threshold = thresholds[min(2, len(thresholds) - 1)]
    warm_threshold = thresholds[0]
    pdf = pdf.copy()
    pdf["is_high"] = pdf["is_high"].astype(bool)

    ax = axes[0, 0]
    bins = np.arange(min(pdf["score"].min(), base_arr.min()) - 0.5, max(pdf["score"].max(), base_arr.max()) + 0.6, 0.5)
    ax.hist(
        base_arr,
        bins=bins,
        color="#4ECDC4",
        alpha=0.6,
        label="Непивотные дни (holdout)",
        edgecolor="black",
        linewidth=0.3,
        weights=np.ones(len(base_arr)) * len(pdf) / len(base_arr),
    )
    ax.hist(pdf["score"], bins=bins, color="#FF6B6B", alpha=0.7, label="Развороты (holdout)", edgecolor="black", linewidth=0.3)
    ax.set_xlabel("Reversal score")
    ax.set_ylabel("Кол-во")
    ax.set_title("Распределение reversal score: holdout развороты vs непивотные дни", fontweight="bold")
    ax.axvline(x=hot_threshold, color="red", linestyle="--", alpha=0.5)
    ax.legend()

    ax = axes[0, 1]
    highs = pdf[pdf["is_high"]]
    lows = pdf[~pdf["is_high"]]
    ax.scatter(highs["date"], highs["score"], c="red", s=60, label="Пики", edgecolors="black", linewidths=0.3, zorder=3)
    ax.scatter(lows["date"], lows["score"], c="green", s=60, label="Дно", edgecolors="black", linewidths=0.3, zorder=3)
    ax.axhline(y=hot_threshold, color="orange", linestyle="--", alpha=0.5)
    ax.set_xlabel("Дата")
    ax.set_ylabel("Reversal score")
    ax.set_title("Reversal score по времени (holdout-период)", fontweight="bold")
    ax.legend(fontsize=8)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    ax = axes[1, 0]
    ax.scatter(highs["direction"], highs["score"], c="red", s=60, label="Пики", edgecolors="black", linewidths=0.3)
    ax.scatter(lows["direction"], lows["score"], c="green", s=60, label="Дно", edgecolors="black", linewidths=0.3)
    ax.axvline(x=0, color="gray", linewidth=0.5)
    ax.axhline(y=hot_threshold, color="orange", linestyle="--", alpha=0.5)
    ax.set_xlabel("Direction bias (>0 = пик, <0 = дно)")
    ax.set_ylabel("Reversal score")
    ax.set_title("Reversal score vs Direction score", fontweight="bold")
    ax.legend()

    ax = axes[1, 1]
    colors = ["#FF6B6B" if s >= hot_threshold else "#FFC107" if s >= warm_threshold else "#4ECDC4" for s in calendar_df["score"]]
    ax.bar(calendar_df["date"], calendar_df["score"], color=colors, edgecolor="none", width=1.0)
    ax.axhline(y=hot_threshold, color="red", linestyle="--", alpha=0.5)
    ax.axhline(y=warm_threshold, color="orange", linestyle="--", alpha=0.3)
    ax.set_xlabel("Дата")
    ax.set_ylabel("Reversal score")
    ax.set_title("Астро-календарь (красный = зоны риска)", fontweight="bold")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    plt.suptitle("BTC Астро-скоринг — Reversal/Direction модели + Календарь", fontsize=16, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig("astro_scoring_results.png", dpi=150, bbox_inches="tight")
    print("\nГрафик: astro_scoring_results.png")
    plt.close()


def _model_fingerprint(model: dict) -> str:
    """Стабильный хеш весов модели для отслеживания изменений."""
    payload = json.dumps(
        {
            "reversal_weights": model["reversal_model"]["weights"],
            "continuous_weights": {
                k: v["weight"] for k, v in model["reversal_model"]["continuous_weights"].items()
            },
            "direction_weights": model["direction_model"]["weights"],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def save_model_metadata(model: dict, split_date: str, train_metrics: dict, test_metrics: dict):
    """Сохраняет версию модели в БД для отслеживания и отката."""
    fingerprint = _model_fingerprint(model)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS btc_model_versions ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  fingerprint TEXT NOT NULL,"
        "  created_at TEXT NOT NULL,"
        "  split_date TEXT,"
        "  shrinkage_factor REAL,"
        "  n_reversal_features INTEGER,"
        "  n_direction_features INTEGER,"
        "  train_mw_p REAL,"
        "  test_mw_p REAL,"
        "  test_direction_accuracy REAL,"
        "  weights_json TEXT"
        ")"
    )
    conn.execute(
        "INSERT INTO btc_model_versions "
        "(fingerprint, created_at, split_date, shrinkage_factor, "
        " n_reversal_features, n_direction_features, "
        " train_mw_p, test_mw_p, test_direction_accuracy, weights_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            fingerprint,
            datetime.now().isoformat(timespec="seconds"),
            split_date,
            WEIGHT_SHRINKAGE_FACTOR,
            len(model["reversal_model"]["weights"]) + len(model["reversal_model"]["continuous_weights"]),
            len(model["direction_model"]["weights"]),
            train_metrics.get("mw_p"),
            test_metrics.get("mw_p"),
            test_metrics.get("direction_accuracy"),
            json.dumps(
                {
                    "reversal": model["reversal_model"]["weights"],
                    "continuous": model["reversal_model"]["continuous_weights"],
                    "direction": model["direction_model"]["weights"],
                },
                ensure_ascii=False,
            ),
        ),
    )
    conn.commit()
    conn.close()
    logger.info("Модель сохранена: fingerprint=%s, shrinkage=%.2f", fingerprint, WEIGHT_SHRINKAGE_FACTOR)
    return fingerprint


def save_calendar_to_db(calendar_df):
    conn = sqlite3.connect(DB_PATH)
    rows = []
    for _, row in calendar_df.iterrows():
        rows.append(
            {
                "date": row["date"].strftime("%Y-%m-%d"),
                "score": row["score"],
                "direction": row["direction"],
                "reversal_score": row["reversal_score"],
                "direction_score": row["direction_score"],
                "moon_sign": row["moon_sign"],
                "moon_element": row["moon_element"],
                "sun_sign": row.get("sun_sign", ""),
                "sun_element": row.get("sun_element", ""),
                "quarter": row["quarter"],
                "eclipse_days": row["eclipse_days"],
                "days_to_eclipse": row["days_to_eclipse"],
                "moon_ingress": int(row["moon_ingress"]),
                "station_strength": row["station_strength"],
                "moon_age_sin": row["moon_age_sin"],
                "moon_age_cos": row["moon_age_cos"],
                "tension": row["tension"],
                "harmony": row["harmony"],
                "retro_planets": ",".join(row["retro_planets"]),
                "station_planets": ",".join(row["station_planets"]),
                "details": " | ".join(row["details"]),
            }
        )
    pd.DataFrame(rows).to_sql("btc_astro_calendar", conn, if_exists="replace", index=False)
    print(f"Сохранено в btc_astro_calendar: {len(rows)} строк")
    conn.close()


def save_history_to_db(history_df):
    conn = sqlite3.connect(DB_PATH)
    rows = []
    for _, row in history_df.iterrows():
        rows.append(
            {
                "date": row["date"].strftime("%Y-%m-%d"),
                "close": row["close"],
                "score": row["score"],
                "direction": row["direction"],
                "reversal_score": row["reversal_score"],
                "direction_score": row["direction_score"],
                "moon_sign": row["moon_sign"],
                "moon_element": row["moon_element"],
                "sun_sign": row.get("sun_sign", ""),
                "sun_element": row.get("sun_element", ""),
                "quarter": row["quarter"],
                "eclipse_days": row["eclipse_days"],
                "days_to_eclipse": row["days_to_eclipse"],
                "moon_ingress": int(row["moon_ingress"]),
                "station_strength": row["station_strength"],
                "moon_age_sin": row["moon_age_sin"],
                "moon_age_cos": row["moon_age_cos"],
                "tension": row["tension"],
                "harmony": row["harmony"],
                "retro_planets": ",".join(row["retro_planets"]),
                "station_planets": ",".join(row["station_planets"]),
                "details": " | ".join(row["details"]),
                "sample_split": row["sample_split"],
                "is_pivot": int(row["is_pivot"]),
            }
        )
    pd.DataFrame(rows).to_sql("btc_astro_history", conn, if_exists="replace", index=False)
    print(f"Сохранено в btc_astro_history: {len(rows)} строк")
    conn.close()


def main():
    (
        history_eval_df, pdf, base_arr, test_metrics, full_model,
        eval_thresholds, history_full_df, full_thresholds,
        train_metrics, split_start,
    ) = validate_model()

    save_model_metadata(
        full_model,
        split_date=split_start.strftime("%Y-%m-%d"),
        train_metrics=train_metrics,
        test_metrics=test_metrics,
    )

    today = datetime.combine(today_local_date(), datetime.min.time())
    end_date = datetime(2028, 12, 31)
    calendar_df = generate_calendar(today, end_date, full_model, full_thresholds)

    plot_results(pdf, base_arr, calendar_df, eval_thresholds)
    save_history_to_db(history_full_df)
    save_calendar_to_db(calendar_df)

    hot_threshold = full_thresholds[min(2, len(full_thresholds) - 1)]
    print(f"\n\n{'=' * 90}")
    print("БЛИЖАЙШИЕ ЗОНЫ РИСКА РАЗВОРОТА")
    print("=" * 90)
    hot = calendar_df[calendar_df["score"] >= hot_threshold].head(15)
    for _, row in hot.iterrows():
        dir_str = "↑ ПИК" if row["direction"] > 0 else "↓ ДНО" if row["direction"] < 0 else "  ?"
        days_away = (row["date"] - today).days
        print(f"\n  {row['date'].strftime('%Y-%m-%d')} (через {days_away}д)  СКОР: {row['score']:.1f}  {dir_str}")
        sun_info = f" | Солнце в {row['sun_sign']}" if row.get("sun_sign") else ""
        print(f"    {row['quarter']} | Луна в {row['moon_sign']} ({row['moon_element']}){sun_info}")
        for detail in row["details"]:
            print(f"    {detail}")


if __name__ == "__main__":
    main()
