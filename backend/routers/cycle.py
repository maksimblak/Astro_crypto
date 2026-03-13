"""Macro cycle endpoints for BTC top/bottom monitoring."""

from __future__ import annotations

from datetime import date, datetime

import duckdb
import pandas as pd
from fastapi import APIRouter, HTTPException

from backend.db import get_db, is_missing_relation
from backend.services import cache_service

CYCLE_CACHE_TTL = 3600  # 1 hour

try:
    from research.cycle_projections import build_projections
except ImportError:
    build_projections = None  # type: ignore[assignment]

router = APIRouter(tags=["cycle"])


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _round_or_none(value, digits: int = 4):
    if value is None:
        return None
    return round(float(value), digits)


def _fmt_float(value, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def _fmt_pct(value, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.{digits}f}%"


def _days_since_event(rows: list[dict], key: str, expected_value: int = 1) -> int | None:
    latest_date = _parse_date(rows[-1]["date"])
    for row in reversed(rows):
        if row.get(key) == expected_value:
            return (latest_date - _parse_date(row["date"])).days
    return None


def _signal_tone(top_score, bottom_score) -> str:
    top = float(top_score or 0.0)
    bottom = float(bottom_score or 0.0)
    if bottom >= max(0.25, top + 0.05):
        return "bull"
    if top >= max(0.25, bottom + 0.05):
        return "bear"
    return "neutral"


def _build_zone_meta(zone: str) -> tuple[str, str, str]:
    mapping = {
        "top_zone": (
            "Зона macro top",
            "bear",
            "Composite score уже в late-cycle зоне: valuation вытянут, а timing-сигналы не спорят с перегревом.",
        ),
        "top_watch": (
            "Top watch",
            "bear",
            "Рынок ещё не в confirmed top zone, но valuation уже близок к историческим верхним диапазонам.",
        ),
        "bottom_zone": (
            "Зона macro bottom",
            "bull",
            "Composite score уже в капитуляционной зоне: valuation дешёвый, а bottom-confirmation слой поддерживает набор позиции.",
        ),
        "bottom_watch": (
            "Bottom watch",
            "bull",
            "Рынок ещё не в финальной зоне дна, но часть макро-индикаторов уже уходит в область перепроданности.",
        ),
        "mixed": (
            "Смешанный фон",
            "neutral",
            "Часть top и bottom сигналов одновременно активна. Для macro-cycle слоя это обычно означает переходную фазу, а не чистый экстремум.",
        ),
    }
    return mapping.get(
        zone,
        (
            "Нейтральный цикл",
            "neutral",
            "Macro-cycle слой не видит сейчас ни устойчивой зоны top, ни подтверждённой зоны bottom.",
        ),
    )


def _build_signals(rows: list[dict]) -> list[dict]:
    latest = rows[-1]
    pi_top_days = _days_since_event(rows, "pi_cycle_signal", 1)
    hash_buy_days = _days_since_event(rows, "hashribbon_buy_signal", 1)

    pi_ratio = None
    if latest.get("pi_sma111") and latest.get("pi_sma350x2"):
        denominator = float(latest["pi_sma350x2"])
        if denominator:
            pi_ratio = float(latest["pi_sma111"]) / denominator - 1.0

    signals = [
        {
            "label": "MVRV Z-Score",
            "value": _fmt_float(latest.get("mvrv_zscore")),
            "tone": _signal_tone(latest.get("mvrv_top_score"), latest.get("mvrv_bottom_score")),
            "note": (
                f"Adaptive top threshold {_fmt_float(latest.get('mvrv_top_threshold'))}; "
                f"bottom extreme {_fmt_float(latest.get('mvrv_bottom_extreme'))}. "
                "MVRV остаётся главным valuation-фильтром для macro extremes."
            ),
        },
        {
            "label": "NUPL",
            "value": _fmt_float(latest.get("nupl"), 3),
            "tone": _signal_tone(latest.get("nupl_top_score"), latest.get("nupl_bottom_score")),
            "note": (
                f"Adaptive top threshold {_fmt_float(latest.get('nupl_top_threshold'), 3)}; "
                f"bottom extreme {_fmt_float(latest.get('nupl_bottom_extreme'), 3)}. "
                "NUPL показывает, насколько рынок сидит в нереализованной прибыли."
            ),
        },
        {
            "label": "Puell Multiple",
            "value": _fmt_float(latest.get("puell_multiple"), 3),
            "tone": _signal_tone(latest.get("puell_top_score"), latest.get("puell_bottom_score")),
            "note": (
                f"Adaptive top threshold {_fmt_float(latest.get('puell_top_threshold'), 2)}; "
                f"bottom extreme {_fmt_float(latest.get('puell_bottom_extreme'), 2)}. "
                "Этот слой отслеживает miner stress и pressure со стороны issuance."
            ),
        },
        {
            "label": "Pi Cycle Top",
            "value": str(int(latest.get("pi_cycle_signal") or 0)),
            "tone": "bear" if (latest.get("pi_cycle_top_score") or 0) > 0 else "neutral",
            "note": (
                f"111DMA vs 2x350DMA: {_fmt_pct(pi_ratio)}. "
                + (
                    f"Последний top crossover был {pi_top_days}д назад."
                    if pi_top_days is not None
                    else "Top crossover в текущем диапазоне данных пока не было."
                )
            ),
        },
        {
            "label": "Hash Ribbons",
            "value": latest.get("hashribbon_trend") or "—",
            "tone": "bull" if (latest.get("hashribbon_bottom_score") or 0) > 0 else "neutral",
            "note": (
                f"30DMA hashrate {_fmt_float(latest.get('hashrate_sma_30'), 0)}, "
                f"60DMA {_fmt_float(latest.get('hashrate_sma_60'), 0)}. "
                + (
                    f"Последний buy-confirmation был {hash_buy_days}д назад."
                    if hash_buy_days is not None
                    else "Buy-confirmation в текущем диапазоне данных пока не было."
                )
            ),
        },
    ]
    return signals


@router.get("/cycle")
def api_cycle():
    cached = cache_service.get("cycle")
    if cached is not None:
        return cached

    try:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT
                    date,
                    price,
                    mvrv_zscore,
                    nupl,
                    puell_multiple,
                    pi_sma111,
                    pi_sma350x2,
                    pi_cycle_signal,
                    hashrate_sma_30,
                    hashrate_sma_60,
                    hashribbon_trend,
                    hashribbon_buy_signal,
                    mvrv_top_threshold,
                    nupl_top_threshold,
                    puell_top_threshold,
                    mvrv_bottom_extreme,
                    nupl_bottom_extreme,
                    puell_bottom_extreme,
                    mvrv_top_score,
                    mvrv_bottom_score,
                    nupl_top_score,
                    nupl_bottom_score,
                    puell_top_score,
                    puell_bottom_score,
                    pi_cycle_top_score,
                    pi_cycle_bottom_score,
                    hashribbon_bottom_score,
                    top_score,
                    bottom_score,
                    cycle_bias,
                    cycle_zone
                FROM btc_cycle_metrics
                ORDER BY date
                """
            ).fetchall()
    except duckdb.Error as exc:
        if is_missing_relation(exc, "btc_cycle_metrics"):
            raise HTTPException(404, "Table btc_cycle_metrics not found. Run research/main.py first.") from exc
        raise HTTPException(500, "Failed to query btc_cycle_metrics.") from exc

    if not rows:
        raise HTTPException(404, "No cycle metric data found in btc_cycle_metrics.")

    latest = rows[-1]
    cycle_label, cycle_tone, summary = _build_zone_meta(latest.get("cycle_zone") or "neutral")
    signals = _build_signals(rows)

    history = [
        {
            "date": row["date"],
            "price": _round_or_none(row.get("price"), 2),
            "top_score": _round_or_none(row.get("top_score"), 4),
            "bottom_score": _round_or_none(row.get("bottom_score"), 4),
            "cycle_bias": _round_or_none(row.get("cycle_bias"), 4),
            "cycle_zone": row.get("cycle_zone") or "neutral",
            "mvrv_zscore": _round_or_none(row.get("mvrv_zscore"), 4),
            "nupl": _round_or_none(row.get("nupl"), 4),
            "puell_multiple": _round_or_none(row.get("puell_multiple"), 4),
            "pi_cycle_signal": row.get("pi_cycle_signal"),
            "hashribbon_buy_signal": row.get("hashribbon_buy_signal"),
        }
        for row in rows
    ]

    result = {
        "as_of": latest["date"],
        "price": _round_or_none(latest.get("price"), 2),
        "cycle_zone": latest.get("cycle_zone") or "neutral",
        "cycle_label": cycle_label,
        "cycle_tone": cycle_tone,
        "summary": summary,
        "top_score": _round_or_none(latest.get("top_score"), 4),
        "bottom_score": _round_or_none(latest.get("bottom_score"), 4),
        "cycle_bias": _round_or_none(latest.get("cycle_bias"), 4),
        "metrics": {
            "mvrv_zscore": _round_or_none(latest.get("mvrv_zscore"), 4),
            "mvrv_top_threshold": _round_or_none(latest.get("mvrv_top_threshold"), 4),
            "mvrv_bottom_extreme": _round_or_none(latest.get("mvrv_bottom_extreme"), 4),
            "nupl": _round_or_none(latest.get("nupl"), 4),
            "nupl_top_threshold": _round_or_none(latest.get("nupl_top_threshold"), 4),
            "nupl_bottom_extreme": _round_or_none(latest.get("nupl_bottom_extreme"), 4),
            "puell_multiple": _round_or_none(latest.get("puell_multiple"), 4),
            "puell_top_threshold": _round_or_none(latest.get("puell_top_threshold"), 4),
            "puell_bottom_extreme": _round_or_none(latest.get("puell_bottom_extreme"), 4),
            "pi_sma111": _round_or_none(latest.get("pi_sma111"), 2),
            "pi_sma350x2": _round_or_none(latest.get("pi_sma350x2"), 2),
            "pi_cycle_signal": latest.get("pi_cycle_signal"),
            "hashrate_sma_30": _round_or_none(latest.get("hashrate_sma_30"), 0),
            "hashrate_sma_60": _round_or_none(latest.get("hashrate_sma_60"), 0),
            "hashribbon_trend": latest.get("hashribbon_trend"),
            "hashribbon_buy_signal": latest.get("hashribbon_buy_signal"),
        },
        "signals": signals,
        "history": history,
        "projections": _build_projections_safe(),
    }
    cache_service.set("cycle", result, ttl=CYCLE_CACHE_TTL)
    return result


def _build_projections_safe() -> dict | None:
    """Build price-only projections from btc_daily OHLCV. Returns None on failure."""
    if build_projections is None:
        return None
    try:
        with get_db() as conn:
            raw = conn.execute(
                "SELECT date, close FROM btc_daily ORDER BY date"
            ).fetchall()
        if not raw:
            return None
        df = pd.DataFrame(raw)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        return build_projections(df)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to build cycle projections")
        return None
