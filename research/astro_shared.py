from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from skyfield.api import Loader, Topos
from skyfield.framelib import ecliptic_frame

try:
    from .config import DB_PATH, today_local_date, yfinance_exclusive_end
except ImportError:
    from config import DB_PATH, today_local_date, yfinance_exclusive_end

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
_EPHEMERIS_NAME = "de421.bsp"
_EPHEMERIS_SEARCH_PATHS = [
    DATA_DIR / _EPHEMERIS_NAME,
    BASE_DIR / _EPHEMERIS_NAME,
]
_ephemeris_path = next((path for path in _EPHEMERIS_SEARCH_PATHS if path.exists()), None)
_sky_loader = Loader(str((_ephemeris_path or (DATA_DIR / _EPHEMERIS_NAME)).parent))

ZODIAC_SIGNS = [
    "Овен", "Телец", "Близнецы", "Рак",
    "Лев", "Дева", "Весы", "Скорпион",
    "Стрелец", "Козерог", "Водолей", "Рыбы",
]

ELEMENT_MAP = {
    "Овен": "Огонь", "Телец": "Земля", "Близнецы": "Воздух", "Рак": "Вода",
    "Лев": "Огонь", "Дева": "Земля", "Весы": "Воздух", "Скорпион": "Вода",
    "Стрелец": "Огонь", "Козерог": "Земля", "Водолей": "Воздух", "Рыбы": "Вода",
}

MODALITY_MAP = {
    "Овен": "Кардинальный", "Телец": "Фиксированный", "Близнецы": "Мутабельный",
    "Рак": "Кардинальный", "Лев": "Фиксированный", "Дева": "Мутабельный",
    "Весы": "Кардинальный", "Скорпион": "Фиксированный", "Стрелец": "Мутабельный",
    "Козерог": "Кардинальный", "Водолей": "Фиксированный", "Рыбы": "Мутабельный",
}

ECLIPSES = [
    ("2020-01-10", "lunar"),
    ("2020-06-05", "lunar"),
    ("2020-06-21", "solar"),
    ("2020-07-05", "lunar"),
    ("2020-11-30", "lunar"),
    ("2020-12-14", "solar"),
    ("2021-05-26", "lunar"),
    ("2021-06-10", "solar"),
    ("2021-11-19", "lunar"),
    ("2021-12-04", "solar"),
    ("2022-04-30", "solar"),
    ("2022-05-16", "lunar"),
    ("2022-10-25", "solar"),
    ("2022-11-08", "lunar"),
    ("2023-04-20", "solar"),
    ("2023-05-05", "lunar"),
    ("2023-10-14", "solar"),
    ("2023-10-28", "lunar"),
    ("2024-03-25", "lunar"),
    ("2024-04-08", "solar"),
    ("2024-09-18", "lunar"),
    ("2024-10-02", "solar"),
    ("2025-03-14", "lunar"),
    ("2025-03-29", "solar"),
    ("2025-09-07", "lunar"),
    ("2025-09-21", "solar"),
    ("2026-02-17", "solar"),
    ("2026-03-03", "lunar"),
    ("2026-08-12", "solar"),
    ("2026-08-28", "lunar"),
    ("2027-02-06", "solar"),
    ("2027-02-20", "lunar"),
    ("2027-08-02", "solar"),
    ("2027-08-17", "lunar"),
    ("2028-01-12", "lunar"),
    ("2028-01-26", "solar"),
    ("2028-07-06", "lunar"),
    ("2028-07-22", "solar"),
    ("2028-12-31", "lunar"),
]
ECLIPSE_DATES = [datetime.strptime(event_date, "%Y-%m-%d") for event_date, _ in ECLIPSES]

# ---------------------------------------------------------------------------
# Skyfield globals (loaded once)
# ---------------------------------------------------------------------------
try:
    _eph = _sky_loader(_EPHEMERIS_NAME)
except OSError as exc:
    searched_paths = ", ".join(str(path) for path in _EPHEMERIS_SEARCH_PATHS)
    raise RuntimeError(
        f"Unable to load {_EPHEMERIS_NAME}. Checked {searched_paths}; "
        "if it is not present locally, automatic download also failed."
    ) from exc
_ts = _sky_loader.timescale()
_earth = _eph["earth"]
_sun = _eph["sun"]
_moon = _eph["moon"]

# Planet lookup by ephem-compatible class name or Russian name
PLANET_TARGETS = {
    "Sun": _sun,
    "Moon": _moon,
    "Mercury": _eph["mercury"],
    "Venus": _eph["venus"],
    "Mars": _eph["mars barycenter"],
    "Jupiter": _eph["jupiter barycenter"],
    "Saturn": _eph["saturn barycenter"],
    "Uranus": _eph["uranus barycenter"],
    "Neptune": _eph["neptune barycenter"],
    "Pluto": _eph["pluto barycenter"],
    "Солнце": _sun,
    "Луна": _moon,
    "Меркурий": _eph["mercury"],
    "Венера": _eph["venus"],
    "Марс": _eph["mars barycenter"],
    "Юпитер": _eph["jupiter barycenter"],
    "Сатурн": _eph["saturn barycenter"],
    "Уран": _eph["uranus barycenter"],
    "Нептун": _eph["neptune barycenter"],
    "Плутон": _eph["pluto barycenter"],
}


def _to_skyfield_time(d):
    """Convert datetime/date to Skyfield Time object."""
    if isinstance(d, datetime):
        return _ts.utc(d.year, d.month, d.day, d.hour, d.minute, d.second)
    if isinstance(d, date):
        return _ts.utc(d.year, d.month, d.day)
    return d  # already a Skyfield Time


def ecliptic_lon_deg_for_target(target, d) -> float:
    """Ecliptic longitude in degrees (0-360) for a Skyfield target at date d."""
    t = _to_skyfield_time(d)
    astrometric = _earth.at(t).observe(target)
    _, lon, _ = astrometric.apparent().frame_latlon(ecliptic_frame)
    return lon.degrees % 360


def ecliptic_lon_deg(body) -> float:
    """Compatibility wrapper: compute ecliptic longitude from a body dict.

    For backward compatibility with code that passes a pre-created 'body'.
    Now body should be a dict with 'target' and 'time' keys.
    """
    if isinstance(body, dict):
        return ecliptic_lon_deg_for_target(body["target"], body["time"])
    raise TypeError(f"ecliptic_lon_deg expects a dict, got {type(body)}")


def planet_lon_deg(name_or_target, d) -> float:
    """Get ecliptic longitude for a planet by name or Skyfield target."""
    if isinstance(name_or_target, str):
        target = PLANET_TARGETS[name_or_target]
    else:
        target = name_or_target
    return ecliptic_lon_deg_for_target(target, d)


def is_retrograde(planet_name: str, d_now, d_prev) -> bool:
    """Planet is retrograde (moving backward in ecliptic longitude)."""
    target = PLANET_TARGETS[planet_name] if isinstance(planet_name, str) else planet_name
    lon_now = ecliptic_lon_deg_for_target(target, d_now)
    lon_prev = ecliptic_lon_deg_for_target(target, d_prev)
    diff = lon_now - lon_prev
    if diff > 180:
        diff -= 360
    elif diff < -180:
        diff += 360
    return bool(diff < 0)


def is_stationary(planet_name: str, d_now, orb_days: int = 2) -> bool:
    """Planet is stationary (changes direction within ±orb_days)."""
    if isinstance(d_now, (date, datetime)):
        dt = d_now if isinstance(d_now, datetime) else datetime(d_now.year, d_now.month, d_now.day)
    else:
        dt = d_now.utc_datetime()
    d_before = dt - timedelta(days=orb_days)
    d_after = dt + timedelta(days=orb_days)

    target = PLANET_TARGETS[planet_name] if isinstance(planet_name, str) else planet_name
    lon_before = ecliptic_lon_deg_for_target(target, d_before)
    lon_now = ecliptic_lon_deg_for_target(target, dt)
    lon_after = ecliptic_lon_deg_for_target(target, d_after)

    def _norm(a: float, b: float) -> float:
        diff = a - b
        if diff > 180:
            diff -= 360
        elif diff < -180:
            diff += 360
        return diff

    d1 = _norm(lon_now, lon_before)
    d2 = _norm(lon_after, lon_now)
    return bool((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0))


# ---------------------------------------------------------------------------
# Moon phases (replacing ephem.previous_new_moon etc.)
# ---------------------------------------------------------------------------

def _moon_sun_elongation(t) -> float:
    """Elongation of Moon from Sun in degrees (0-360)."""
    sun_lon = ecliptic_lon_deg_for_target(_sun, t)
    moon_lon = ecliptic_lon_deg_for_target(_moon, t)
    return (moon_lon - sun_lon) % 360


def _find_phase(d, target_elongation: float, direction: str = "previous") -> datetime:
    """Find nearest new/full/quarter moon by searching for target elongation.

    target_elongation: 0=new, 90=first quarter, 180=full, 270=last quarter
    direction: 'previous' or 'next'
    """
    if isinstance(d, (date, datetime)):
        dt = d if isinstance(d, datetime) else datetime(d.year, d.month, d.day)
    else:
        dt = d.utc_datetime()

    step = timedelta(days=-1 if direction == "previous" else 1)
    current = dt

    # Coarse search (1-day steps, up to 35 days)
    prev_diff = None
    for _ in range(35):
        elong = _moon_sun_elongation(current)
        diff = (elong - target_elongation) % 360
        if diff > 180:
            diff -= 360
        if prev_diff is not None:
            if (direction == "previous" and prev_diff <= 0 < diff) or \
               (direction == "next" and prev_diff >= 0 > diff):
                # Crossed the target — refine between current-step and current
                break
        prev_diff = diff
        current += step

    # Fine search (binary search, 1-minute precision)
    a = current - step
    b = current
    for _ in range(20):
        mid = a + (b - a) / 2
        elong = _moon_sun_elongation(mid)
        diff = (elong - target_elongation) % 360
        if diff > 180:
            diff -= 360
        if abs(diff) < 0.01:
            return mid
        if diff > 0:
            if direction == "previous":
                b = mid
            else:
                a = mid
        else:
            if direction == "previous":
                a = mid
            else:
                b = mid
    return a + (b - a) / 2


def previous_new_moon(d) -> datetime:
    return _find_phase(d, 0, "previous")


def next_new_moon(d) -> datetime:
    return _find_phase(d, 0, "next")


def previous_full_moon(d) -> datetime:
    return _find_phase(d, 180, "previous")


def next_full_moon(d) -> datetime:
    return _find_phase(d, 180, "next")


def previous_first_quarter_moon(d) -> datetime:
    return _find_phase(d, 90, "previous")


def next_first_quarter_moon(d) -> datetime:
    return _find_phase(d, 90, "next")


def previous_last_quarter_moon(d) -> datetime:
    return _find_phase(d, 270, "previous")


def next_last_quarter_moon(d) -> datetime:
    return _find_phase(d, 270, "next")


def moon_phase_percent(d) -> float:
    """Moon phase as percentage (0=new, 100=full), matching ephem.Moon.phase."""
    elong = _moon_sun_elongation(d)
    # Phase percent: 0 at new (0°), 100 at full (180°)
    return (1 - math.cos(math.radians(elong))) / 2 * 100


def julian_date(d) -> float:
    """Julian Date for a datetime, replacing ephem.julian_date."""
    t = _to_skyfield_time(d)
    return t.tt


# ---------------------------------------------------------------------------
# Utility functions unchanged from before
# ---------------------------------------------------------------------------

def get_zodiac_sign(lon_deg: float) -> str:
    return ZODIAC_SIGNS[int(lon_deg % 360 / 30)]


def apply_bh_correction(records: list[dict], p_key: str = "p_value", q_key: str = "q_value") -> list[dict]:
    if not records:
        return records

    ranked = sorted(
        ((idx, float(record[p_key])) for idx, record in enumerate(records)),
        key=lambda item: item[1],
    )
    total = len(ranked)
    q_values = [1.0] * total
    running_min = 1.0

    for offset in range(total - 1, -1, -1):
        _, p_value = ranked[offset]
        rank = offset + 1
        adjusted = min(1.0, p_value * total / rank)
        running_min = min(running_min, adjusted)
        q_values[offset] = running_min

    for (idx, _), q_value in zip(ranked, q_values):
        records[idx][q_key] = round(q_value, 4)

    return records
