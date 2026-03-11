"""Market regime calculation for the BTC dashboard."""

from __future__ import annotations

from math import sqrt
from statistics import mean, pstdev


def _avg(values):
    return mean(values) if values else None


def _std(values):
    if len(values) < 2:
        return None
    return pstdev(values)


def _pct_change(current, previous):
    if current is None or previous in (None, 0):
        return None
    return current / previous - 1.0


def _fmt_pct(value, digits=1):
    if value is None:
        return "—"
    return f"{value * 100:.{digits}f}%"


def _fmt_ratio(value, digits=2):
    if value is None:
        return "—"
    return f"{value:.{digits}f}x"


def _take(values, end_idx, window):
    start = max(0, end_idx - window + 1)
    return values[start : end_idx + 1]


def _rolling_percentile(current, history):
    values = [item for item in history if item is not None]
    if current is None or not values:
        return None
    return sum(1 for item in values if item <= current) / len(values)


def _candidate_score(checks):
    valid = [check for check in checks if check is not None]
    if not valid:
        return 0.0
    return sum(1 for check in valid if check) / len(valid)


def _check(value, predicate):
    if value is None:
        return None
    return predicate(value)


def _signal_tone(value):
    if value > 0:
        return "bull"
    if value < 0:
        return "bear"
    return "neutral"


def _build_signals(metrics):
    signals = []

    close_vs_200 = metrics["close_vs_200"]
    if close_vs_200 is None:
        close_impact = 0
    elif close_vs_200 > 0:
        close_impact = 2
    else:
        close_impact = -2
    signals.append(
        {
            "label": "Цена vs 200DMA",
            "value": _fmt_pct(close_vs_200),
            "note": "Выше 200DMA = структурный risk-on.",
            "impact": close_impact,
            "tone": _signal_tone(close_impact),
        }
    )

    sma50_vs_200 = metrics["sma50_vs_200"]
    if sma50_vs_200 is None:
        cross_impact = 0
    elif sma50_vs_200 > 0:
        cross_impact = 1
    else:
        cross_impact = -1
    signals.append(
        {
            "label": "50DMA vs 200DMA",
            "value": _fmt_pct(sma50_vs_200),
            "note": "Показывает, подтверждает ли средний тренд базовый режим.",
            "impact": cross_impact,
            "tone": _signal_tone(cross_impact),
        }
    )

    mom20 = metrics["momentum_20"]
    if mom20 is None:
        mom20_impact = 0
    elif mom20 > 0.03:
        mom20_impact = 1
    elif mom20 < -0.03:
        mom20_impact = -1
    else:
        mom20_impact = 0
    signals.append(
        {
            "label": "Импульс 20д",
            "value": _fmt_pct(mom20),
            "note": "Локальный импульс. Полезен для свежего ускорения или срыва.",
            "impact": mom20_impact,
            "tone": _signal_tone(mom20_impact),
        }
    )

    mom90 = metrics["momentum_90"]
    if mom90 is None:
        mom90_impact = 0
    elif mom90 > 0.10:
        mom90_impact = 2
    elif mom90 > 0:
        mom90_impact = 1
    elif mom90 < -0.10:
        mom90_impact = -2
    elif mom90 < 0:
        mom90_impact = -1
    else:
        mom90_impact = 0
    signals.append(
        {
            "label": "Импульс 90д",
            "value": _fmt_pct(mom90),
            "note": "Среднесрочный драйвер режима. Один из самых полезных сигналов.",
            "impact": mom90_impact,
            "tone": _signal_tone(mom90_impact),
        }
    )

    vol_pct = metrics["vol_percentile"]
    if vol_pct is None:
        vol_impact = 0
    elif vol_pct >= 0.85:
        vol_impact = -2
    elif vol_pct >= 0.70:
        vol_impact = -1
    else:
        vol_impact = 0
    signals.append(
        {
            "label": "Vol percentile",
            "value": _fmt_pct(vol_pct),
            "note": "Высокая realized vol чаще мешает устойчивому тренду.",
            "impact": vol_impact,
            "tone": _signal_tone(vol_impact),
        }
    )

    drawdown = metrics["drawdown_ath"]
    if drawdown is None:
        dd_impact = 0
    elif drawdown <= -0.35:
        dd_impact = -2
    elif drawdown <= -0.20:
        dd_impact = -1
    elif drawdown >= -0.10:
        dd_impact = 1
    else:
        dd_impact = 0
    signals.append(
        {
            "label": "Просадка от ATH",
            "value": _fmt_pct(drawdown),
            "note": "Глубокая просадка усиливает стрессовый режим.",
            "impact": dd_impact,
            "tone": _signal_tone(dd_impact),
        }
    )

    volume_z = metrics["volume_z_20"]
    if volume_z is None:
        volume_impact = 0
    elif volume_z >= 1.5 and metrics["momentum_20"] and metrics["momentum_20"] > 0:
        volume_impact = 1
    elif volume_z >= 1.5 and metrics["momentum_20"] and metrics["momentum_20"] < 0:
        volume_impact = -1
    else:
        volume_impact = 0
    signals.append(
        {
            "label": "Volume z-score",
            "value": _fmt_ratio(volume_z),
            "note": "Всплеск объёма усиливает текущее движение, но сам по себе не задаёт тренд.",
            "impact": volume_impact,
            "tone": _signal_tone(volume_impact),
        }
    )

    atr_pct = metrics["atr_pct_14"]
    if atr_pct is None:
        atr_impact = 0
    elif atr_pct >= 0.055:
        atr_impact = -2
    elif atr_pct >= 0.035:
        atr_impact = -1
    else:
        atr_impact = 0
    signals.append(
        {
            "label": "ATR 14д / Цена",
            "value": _fmt_pct(atr_pct),
            "note": "Показывает, насколько дневной диапазон сейчас агрессивен.",
            "impact": atr_impact,
            "tone": _signal_tone(atr_impact),
        }
    )

    return signals


def _classify_regime(metrics):
    close_vs_200 = metrics["close_vs_200"]
    close_vs_50 = metrics["close_vs_50"]
    sma50_vs_200 = metrics["sma50_vs_200"]
    mom20 = metrics["momentum_20"]
    mom90 = metrics["momentum_90"]
    drawdown = metrics["drawdown_ath"]
    vol_pct = metrics["vol_percentile"]
    atr_pct = metrics["atr_pct_14"]
    volume_z = metrics["volume_z_20"]

    candidates = [
        {
            "code": "panic",
            "label": "Паника / распродажа",
            "bias": "risk-off",
            "checks": [
                _check(close_vs_200, lambda value: value < 0),
                _check(mom20, lambda value: value < -0.08),
                _check(drawdown, lambda value: value <= -0.25),
                _check(vol_pct, lambda value: value >= 0.80),
                _check(atr_pct, lambda value: value >= 0.05),
                _check(volume_z, lambda value: value >= 1.0),
            ],
            "summary": "Рынок в stress-режиме: высокая волатильность, слабый импульс и глубокая просадка.",
        },
        {
            "code": "bull",
            "label": "Бычий тренд",
            "bias": "risk-on",
            "checks": [
                _check(close_vs_200, lambda value: value > 0),
                _check(sma50_vs_200, lambda value: value > 0),
                _check(mom90, lambda value: value > 0.10),
                _check(mom20, lambda value: value > 0.03),
                _check(drawdown, lambda value: value > -0.18),
                _check(vol_pct, lambda value: value < 0.75),
            ],
            "summary": "Структура рынка направлена вверх: цена держится над длинными средними и momentum положительный.",
        },
        {
            "code": "bear",
            "label": "Медвежий тренд",
            "bias": "risk-off",
            "checks": [
                _check(close_vs_200, lambda value: value < 0),
                _check(sma50_vs_200, lambda value: value < 0),
                _check(mom90, lambda value: value < -0.10),
                _check(mom20, lambda value: value < -0.03),
                _check(drawdown, lambda value: value <= -0.20),
                _check(vol_pct, lambda value: value >= 0.45),
            ],
            "summary": "Структурно слабый рынок: цена ниже 200DMA и среднесрочный импульс отрицательный.",
        },
        {
            "code": "recovery",
            "label": "Восстановление",
            "bias": "risk-on",
            "checks": [
                _check(close_vs_50, lambda value: value > 0),
                _check(mom20, lambda value: value > 0.03),
                _check(mom90, lambda value: value > 0),
                _check(drawdown, lambda value: -0.35 < value <= -0.10),
                _check(vol_pct, lambda value: value < 0.80),
            ],
            "summary": "Рынок пытается выйти из просадки: локальный импульс уже положительный, но ATH ещё далеко.",
        },
        {
            "code": "distribution",
            "label": "Распределение",
            "bias": "risk-off",
            "checks": [
                _check(close_vs_50, lambda value: value < 0),
                _check(mom20, lambda value: value <= 0),
                _check(mom90, lambda value: value <= 0.05),
                _check(drawdown, lambda value: value < -0.10),
                _check(close_vs_200, lambda value: value > -0.10),
            ],
            "summary": "Тренд выдыхается: рынок не в панике, но сила движения вниз/вбок накапливается.",
        },
        {
            "code": "range",
            "label": "Боковик / chop",
            "bias": "neutral",
            "checks": [
                _check(mom20, lambda value: abs(value) < 0.04),
                _check(mom90, lambda value: abs(value) < 0.10),
                _check(close_vs_50, lambda value: abs(value) < 0.05),
                _check(sma50_vs_200, lambda value: abs(value) < 0.08),
                _check(vol_pct, lambda value: value < 0.65),
            ],
            "summary": "Нет сильного доминирующего тренда: рынок пилит диапазон и плохо подходит под агрессивные directional идеи.",
        },
    ]

    ranked = []
    for idx, candidate in enumerate(candidates):
        score = _candidate_score(candidate["checks"])
        ranked.append((score, -idx, candidate))

    _, _, winner = max(ranked, key=lambda item: (item[0], item[1]))
    confidence = round(_candidate_score(winner["checks"]) * 100)
    return winner, confidence


def build_regime_payload(rows):
    if not rows:
        return {
            "as_of": None,
            "price": None,
            "regime_code": "unknown",
            "regime_label": "Недостаточно данных",
            "bias": "neutral",
            "confidence": 0,
            "regime_score": 0,
            "stress_score": 0,
            "summary": "В таблице btc_daily нет данных для построения режима.",
            "signals": [],
            "metrics": {},
            "history": [],
        }

    closes = [row["close"] for row in rows]
    highs = [row["high"] for row in rows]
    lows = [row["low"] for row in rows]
    volumes = [row["volume"] for row in rows]

    history = []
    returns = []
    rolling_ath = 0.0
    latest_metrics = None
    latest_winner = None

    for idx, close in enumerate(closes):
        prev_close = closes[idx - 1] if idx > 0 else None
        returns.append(_pct_change(close, prev_close))

    rv20_annualized_series = []
    for idx in range(len(rows)):
        return_window = [item for item in _take(returns, idx, 20) if item is not None]
        rv20 = _std(return_window)
        rv20_annualized_series.append(rv20 * sqrt(365) if rv20 is not None else None)

    for idx, row in enumerate(rows):
        close = row["close"]

        rolling_ath = max(rolling_ath, close)
        drawdown_ath = _pct_change(close, rolling_ath)

        sma20 = _avg(_take(closes, idx, 20))
        sma50 = _avg(_take(closes, idx, 50))
        sma200 = _avg(_take(closes, idx, 200))

        momentum_20 = _pct_change(close, closes[idx - 20]) if idx >= 20 else None
        momentum_90 = _pct_change(close, closes[idx - 90]) if idx >= 90 else None

        rv20_annualized = rv20_annualized_series[idx]
        vol_percentile = _rolling_percentile(rv20_annualized, _take(rv20_annualized_series, idx, 252))

        volume_window = _take(volumes, idx, 20)
        volume_mean = _avg(volume_window)
        volume_std = _std(volume_window)
        volume_z_20 = None
        if volume_mean is not None and volume_std not in (None, 0):
            volume_z_20 = (row["volume"] - volume_mean) / volume_std

        tr_values = []
        for j in range(max(1, idx - 13), idx + 1):
            tr = max(
                highs[j] - lows[j],
                abs(highs[j] - closes[j - 1]),
                abs(lows[j] - closes[j - 1]),
            )
            tr_values.append(tr)
        atr_pct_14 = (_avg(tr_values) / close) if tr_values else None

        close_vs_50 = _pct_change(close, sma50) if sma50 else None
        close_vs_200 = _pct_change(close, sma200) if sma200 else None
        sma50_vs_200 = _pct_change(sma50, sma200) if sma50 and sma200 else None

        metrics = {
            "date": row["date"],
            "close": close,
            "volume": row["volume"],
            "sma20": sma20,
            "sma50": sma50,
            "sma200": sma200,
            "close_vs_50": close_vs_50,
            "close_vs_200": close_vs_200,
            "sma50_vs_200": sma50_vs_200,
            "momentum_20": momentum_20,
            "momentum_90": momentum_90,
            "rv20_annualized": rv20_annualized,
            "vol_percentile": vol_percentile,
            "drawdown_ath": drawdown_ath,
            "volume_z_20": volume_z_20,
            "atr_pct_14": atr_pct_14,
        }

        winner, confidence = _classify_regime(metrics)
        signals = _build_signals(metrics)
        trend_score = sum(signal["impact"] for signal in signals)
        stress_score = sum(
            1
            for flag in [
                metrics["vol_percentile"] is not None and metrics["vol_percentile"] >= 0.80,
                metrics["drawdown_ath"] is not None and metrics["drawdown_ath"] <= -0.20,
                metrics["momentum_20"] is not None and metrics["momentum_20"] < -0.05,
                metrics["atr_pct_14"] is not None and metrics["atr_pct_14"] >= 0.05,
            ]
            if flag
        )

        history.append(
            {
                "date": row["date"],
                "close": round(close, 2),
                "regime_code": winner["code"],
                "regime_label": winner["label"],
                "bias": winner["bias"],
                "confidence": confidence,
                "regime_score": trend_score,
                "stress_score": stress_score,
                "momentum_20": round(momentum_20 * 100, 2) if momentum_20 is not None else None,
                "momentum_90": round(momentum_90 * 100, 2) if momentum_90 is not None else None,
                "drawdown_ath": round(drawdown_ath * 100, 2) if drawdown_ath is not None else None,
                "vol_percentile": round(vol_percentile * 100, 1) if vol_percentile is not None else None,
            }
        )
        latest_metrics = metrics
        latest_winner = winner

    latest_point = history[-1]
    latest_signals = _build_signals(latest_metrics)

    return {
        "as_of": latest_point["date"],
        "price": latest_point["close"],
        "regime_code": latest_point["regime_code"],
        "regime_label": latest_point["regime_label"],
        "bias": latest_point["bias"],
        "confidence": latest_point["confidence"],
        "regime_score": latest_point["regime_score"],
        "stress_score": latest_point["stress_score"],
        "summary": latest_winner["summary"],
        "signals": latest_signals,
        "metrics": {
            "momentum_20": latest_point["momentum_20"],
            "momentum_90": latest_point["momentum_90"],
            "drawdown_ath": latest_point["drawdown_ath"],
            "vol_percentile": latest_point["vol_percentile"],
        },
        "history": history[-540:],
    }
