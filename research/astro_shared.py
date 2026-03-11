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
