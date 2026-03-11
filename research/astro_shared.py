from __future__ import annotations

import os
from datetime import date, datetime, timedelta


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "btc_research.db")

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
    ("2027-02-06", "lunar"),
    ("2027-02-20", "solar"),
    ("2027-07-18", "lunar"),
    ("2027-08-02", "solar"),
    ("2027-08-17", "lunar"),
    ("2028-01-12", "lunar"),
    ("2028-01-26", "solar"),
    ("2028-07-06", "lunar"),
    ("2028-07-22", "solar"),
    ("2028-12-31", "lunar"),
]
ECLIPSE_DATES = [datetime.strptime(event_date, "%Y-%m-%d") for event_date, _ in ECLIPSES]

RETROGRADES_KNOWN = [
    ("2026-02-26", "2026-03-20", "Mercury"),
    ("2026-06-29", "2026-07-23", "Mercury"),
    ("2026-10-24", "2026-11-13", "Mercury"),
    ("2027-02-09", "2027-03-03", "Mercury"),
    ("2027-06-10", "2027-07-04", "Mercury"),
    ("2027-10-07", "2027-10-28", "Mercury"),
    ("2028-01-24", "2028-02-14", "Mercury"),
    ("2028-05-21", "2028-06-13", "Mercury"),
    ("2028-09-19", "2028-10-11", "Mercury"),
    ("2026-10-03", "2026-11-13", "Venus"),
    ("2028-05-10", "2028-06-22", "Venus"),
    ("2027-01-10", "2027-04-01", "Mars"),
    ("2026-12-12", "2027-04-12", "Jupiter"),
    ("2028-01-12", "2028-05-13", "Jupiter"),
    ("2026-07-26", "2026-12-10", "Saturn"),
    ("2027-08-09", "2027-12-23", "Saturn"),
    ("2028-08-22", "2029-01-05", "Saturn"),
    ("2026-09-10", "2027-02-08", "Uranus"),
    ("2027-09-15", "2028-02-12", "Uranus"),
    ("2028-09-18", "2029-02-16", "Uranus"),
    ("2026-07-04", "2026-12-10", "Neptune"),
    ("2027-07-09", "2027-12-15", "Neptune"),
    ("2028-07-13", "2028-12-19", "Neptune"),
    ("2026-05-06", "2026-10-15", "Pluto"),
    ("2027-05-08", "2027-10-17", "Pluto"),
    ("2028-05-11", "2028-10-19", "Pluto"),
]

MAJOR_TRANSITS = [
    ("2026-02-09", "Нептун входит в Овен"),
    ("2026-02-18", "Сатурн входит в Овен"),
    ("2026-02-20", "Соединение Сатурн-Нептун 0° Овен"),
    ("2026-05-03", "Уран входит в Близнецы"),
    ("2026-07-02", "Юпитер входит во Лев"),
    ("2026-07-27", "Лунные узлы переходят в Лев/Водолей"),
    ("2026-07-18", "Трин Уран-Плутон #1"),
    ("2026-11-29", "Трин Уран-Плутон #2"),
    ("2027-06-15", "Трин Уран-Плутон #3"),
    ("2027-07-29", "Юпитер входит в Деву"),
    ("2028-01-13", "Трин Уран-Плутон #4"),
    ("2028-03-26", "Лунные узлы переходят в Рак/Козерог"),
    ("2028-04-17", "Сатурн входит в Телец"),
    ("2028-05-09", "Трин Уран-Плутон #5"),
    ("2028-08-27", "Юпитер входит в Весы"),
]
MAJOR_TRANSIT_DATES = {datetime.strptime(event_date, "%Y-%m-%d"): desc for event_date, desc in MAJOR_TRANSITS}


def get_zodiac_sign(lon_deg: float) -> str:
    return ZODIAC_SIGNS[int(lon_deg % 360 / 30)]


def today_local_date() -> date:
    return datetime.now().astimezone().date()


def yfinance_exclusive_end(base_date: date | None = None) -> str:
    current_date = base_date or today_local_date()
    return (current_date + timedelta(days=1)).isoformat()


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
