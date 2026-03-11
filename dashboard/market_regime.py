"""Market regime calculation for the BTC dashboard."""

from __future__ import annotations

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


def _signal_tone(value):
    if value > 0:
        return "bull"
    if value < 0:
        return "bear"
    return "neutral"


def _stress_tone(points):
    if points >= 2:
        return "bear"
    if points == 1:
        return "neutral"
    return "bull"


def _direction_signal(label, value, note, impact, available=True):
    return {
        "label": label,
        "value": value,
        "note": note,
        "impact": impact,
        "tone": _signal_tone(impact),
        "category": "direction",
        "available": available,
    }


def _stress_signal(label, value, note, points, available=True):
    return {
        "label": label,
        "value": value,
        "note": note,
        "points": points,
        "tone": _stress_tone(points),
        "category": "stress",
        "available": available,
    }


def _direction_confidence(direction_signals, direction_score, stress_score, regime_code):
    available = [signal for signal in direction_signals if signal["available"]]
    if not available:
        return 0

    max_abs = sum(abs(signal["impact"]) for signal in available)
    aligned = sum(
        abs(signal["impact"])
        for signal in available
        if signal["impact"] != 0
        and (
            (direction_score > 0 and signal["impact"] > 0)
            or (direction_score < 0 and signal["impact"] < 0)
        )
    )

    available_count = len(available)
    cap = 100 if available_count >= 5 else 85 if available_count >= 3 else 65

    if regime_code == "range":
        disagreement = min(1.0, abs(direction_score) / max(max_abs, 1))
        confidence = round((1.0 - disagreement) * 100 - stress_score * 6)
        return max(25, min(cap, confidence))

    confidence = round(aligned / max(max_abs, 1) * 100)
    if regime_code in {"bull", "recovery"} and stress_score <= 1:
        confidence += 4
    return max(25, min(cap, confidence))


def _stress_profile(stress_score):
    if stress_score >= 5:
        return {
            "stress_label": "Капитуляция",
            "stress_tone": "bear",
            "stress_summary": "Stress extreme: волатильность и просадка уже сами стали отдельным фактором.",
        }
    if stress_score >= 3:
        return {
            "stress_label": "Высокий stress",
            "stress_tone": "bear",
            "stress_summary": "Stress высокий: движение может быть резким, но это не равнозначно направлению.",
        }
    if stress_score >= 1:
        return {
            "stress_label": "Повышенный stress",
            "stress_tone": "neutral",
            "stress_summary": "Stress выше нормы: directional-сигналы лучше читать осторожнее.",
        }
    return {
        "stress_label": "Спокойный фон",
        "stress_tone": "bull",
        "stress_summary": "Stress низкий: рынок читается через тренд и momentum, а не через турбулентность.",
    }


def _classify_regime(metrics, direction_score, stress_score):
    close_vs_200 = metrics["close_vs_200"]
    drawdown = metrics["drawdown_ath"]

    if direction_score >= 10:
        if (drawdown is not None and drawdown <= -0.18) or (close_vs_200 is not None and close_vs_200 <= 0):
            return {
                "code": "recovery",
                "label": "Восстановление",
                "bias": "risk-on",
                "summary": "Направление уже вверх, но рынок всё ещё выходит из прошлой просадки.",
            }
        return {
            "code": "bull",
            "label": "Бычий тренд",
            "bias": "risk-on",
            "summary": "Сильный направленный режим: 200DMA, momentum и drawdown подтверждают устойчивый uptrend.",
        }

    if direction_score >= 4:
        if drawdown is not None and drawdown <= -0.10:
            return {
                "code": "recovery",
                "label": "Восстановление",
                "bias": "risk-on",
                "summary": "Direction стал положительным, но рынок всё ещё не вышел из зоны прошлой слабости.",
            }
        return {
            "code": "bull",
            "label": "Бычий тренд",
            "bias": "risk-on",
            "summary": "Direction устойчиво положительный: среднесрочный импульс и длинные средние смотрят вверх.",
        }

    if direction_score <= -11:
        return {
            "code": "bear",
            "label": "Медвежий тренд",
            "bias": "risk-off",
            "summary": "Сильный downtrend: рынок ниже длинных средних, а momentum остаётся отрицательным.",
        }

    if direction_score <= -6:
        return {
            "code": "bear",
            "label": "Медвежий тренд",
            "bias": "risk-off",
            "summary": "Direction отрицательный по ключевым трендовым сигналам. Преимущество пока на стороне продавцов.",
        }

    if direction_score <= -2:
        return {
            "code": "distribution",
            "label": "Распределение",
            "bias": "risk-off",
            "summary": "Направление уже ухудшилось, но это ещё не капитуляция. Рынок чаще сдаёт структуру, чем падает импульсно.",
        }

    return {
        "code": "range",
        "label": "Боковик / chop",
        "bias": "neutral",
        "summary": "Сильного directional edge сейчас нет. Лучше относиться к рынку как к диапазону, а не к тренду.",
    }


def _build_direction_signals(metrics):
    close_vs_200 = metrics["close_vs_200"]
    if close_vs_200 is None:
        close_impact = 0
    elif close_vs_200 > 0.10:
        close_impact = 3
    elif close_vs_200 > 0:
        close_impact = 2
    elif close_vs_200 <= -0.10:
        close_impact = -3
    else:
        close_impact = -2

    sma50_vs_200 = metrics["sma50_vs_200"]
    if sma50_vs_200 is None:
        cross_impact = 0
    elif sma50_vs_200 > 0.05:
        cross_impact = 2
    elif sma50_vs_200 > 0:
        cross_impact = 1
    elif sma50_vs_200 <= -0.05:
        cross_impact = -2
    else:
        cross_impact = -1

    mom20 = metrics["momentum_20"]
    if mom20 is None:
        mom20_impact = 0
    elif mom20 > 0.08:
        mom20_impact = 2
    elif mom20 > 0.03:
        mom20_impact = 1
    elif mom20 < -0.08:
        mom20_impact = -2
    elif mom20 < -0.03:
        mom20_impact = -1
    else:
        mom20_impact = 0

    mom90 = metrics["momentum_90"]
    if mom90 is None:
        mom90_impact = 0
    elif mom90 > 0.25:
        mom90_impact = 5
    elif mom90 > 0.10:
        mom90_impact = 4
    elif mom90 > 0:
        mom90_impact = 2
    elif mom90 < -0.25:
        mom90_impact = -5
    elif mom90 < -0.10:
        mom90_impact = -4
    elif mom90 < 0:
        mom90_impact = -2
    else:
        mom90_impact = 0

    drawdown = metrics["drawdown_ath"]
    if drawdown is None:
        drawdown_impact = 0
    elif drawdown >= -0.10:
        drawdown_impact = 3
    elif drawdown > -0.20:
        drawdown_impact = 1
    elif drawdown <= -0.50:
        drawdown_impact = -4
    elif drawdown <= -0.35:
        drawdown_impact = -3
    elif drawdown <= -0.20:
        drawdown_impact = -2
    else:
        drawdown_impact = 0

    volume_z = metrics["volume_z_20"]
    if volume_z is None or mom20 is None or volume_z < 1.5:
        volume_impact = 0
    elif mom20 > 0:
        volume_impact = 1
    elif mom20 < 0:
        volume_impact = -1
    else:
        volume_impact = 0

    return [
        _direction_signal(
            "Цена vs 200DMA",
            _fmt_pct(close_vs_200),
            "Главный structural filter. Если BTC ниже 200DMA, directional edge обычно слабее.",
            close_impact,
            close_vs_200 is not None,
        ),
        _direction_signal(
            "50DMA vs 200DMA",
            _fmt_pct(sma50_vs_200),
            "Подтверждение тренда средней длины. Усиливает или ослабляет основной режим.",
            cross_impact,
            sma50_vs_200 is not None,
        ),
        _direction_signal(
            "Импульс 20д",
            _fmt_pct(mom20),
            "Короткий momentum. Используется как дополнительный слой, а не как ядро режима.",
            mom20_impact,
            mom20 is not None,
        ),
        _direction_signal(
            "Импульс 90д",
            _fmt_pct(mom90),
            "Самый сильный directional-сигнал в модели: он задаёт среднесрочный уклон рынка.",
            mom90_impact,
            mom90 is not None,
        ),
        _direction_signal(
            "Просадка от ATH",
            _fmt_pct(drawdown),
            "Неглубокая просадка чаще совместима с продолжением тренда. Глубокая ломает directional edge.",
            drawdown_impact,
            drawdown is not None,
        ),
        _direction_signal(
            "Volume spike по тренду",
            _fmt_ratio(volume_z),
            "Всплеск объёма учитывается только как усиление уже существующего short-term направления.",
            volume_impact,
            volume_z is not None and mom20 is not None,
        ),
    ]


def _build_stress_signals(metrics):
    drawdown = metrics["drawdown_ath"]
    if drawdown is None:
        drawdown_points = 0
    elif drawdown <= -0.50:
        drawdown_points = 3
    elif drawdown <= -0.35:
        drawdown_points = 2
    elif drawdown <= -0.20:
        drawdown_points = 1
    else:
        drawdown_points = 0

    volume_z = metrics["volume_z_20"]
    volume_points = 1 if volume_z is not None and abs(volume_z) >= 2.0 else 0

    mom20 = metrics["momentum_20"]
    momentum_points = 1 if mom20 is not None and mom20 <= -0.08 else 0

    return [
        _stress_signal(
            "Просадка как stress",
            _fmt_pct(drawdown),
            "Глубокая просадка усиливает хрупкость режима, даже если рынок пытается отскакивать.",
            drawdown_points,
            drawdown is not None,
        ),
        _stress_signal(
            "Объёмный шок",
            _fmt_ratio(volume_z),
            "Сильный объёмный выброс повышает турбулентность, но сам по себе не равен тренду.",
            volume_points,
            volume_z is not None,
        ),
        _stress_signal(
            "Импульсный стресс 20д",
            _fmt_pct(mom20),
            "Резкий короткий спад добавляет stress, но не должен доминировать над 90-дневным трендом.",
            momentum_points,
            mom20 is not None,
        ),
    ]


def calculate_regime_history(rows):
    closes = [row["close"] for row in rows]
    volumes = [row["volume"] for row in rows]

    history = []
    rolling_ath = 0.0
    latest_metrics = None
    latest_direction_signals = []
    latest_stress_signals = []
    latest_regime = None

    for idx, row in enumerate(rows):
        close = row["close"]
        rolling_ath = max(rolling_ath, close)
        drawdown_ath = _pct_change(close, rolling_ath)

        sma50 = _avg(_take(closes, idx, 50))
        sma200 = _avg(_take(closes, idx, 200))
        momentum_20 = _pct_change(close, closes[idx - 20]) if idx >= 20 else None
        momentum_90 = _pct_change(close, closes[idx - 90]) if idx >= 90 else None

        volume_window = _take(volumes, idx, 20)
        volume_mean = _avg(volume_window)
        volume_std = _std(volume_window)
        volume_z_20 = None
        if volume_mean is not None and volume_std not in (None, 0):
            volume_z_20 = (row["volume"] - volume_mean) / volume_std

        close_vs_50 = _pct_change(close, sma50) if sma50 else None
        close_vs_200 = _pct_change(close, sma200) if sma200 else None
        sma50_vs_200 = _pct_change(sma50, sma200) if sma50 and sma200 else None

        metrics = {
            "date": row["date"],
            "close": close,
            "volume": row["volume"],
            "sma50": sma50,
            "sma200": sma200,
            "close_vs_50": close_vs_50,
            "close_vs_200": close_vs_200,
            "sma50_vs_200": sma50_vs_200,
            "momentum_20": momentum_20,
            "momentum_90": momentum_90,
            "drawdown_ath": drawdown_ath,
            "volume_z_20": volume_z_20,
        }

        direction_signals = _build_direction_signals(metrics)
        stress_signals = _build_stress_signals(metrics)
        direction_score = sum(signal["impact"] for signal in direction_signals)
        stress_score = sum(signal["points"] for signal in stress_signals)
        regime = _classify_regime(metrics, direction_score, stress_score)
        confidence = _direction_confidence(direction_signals, direction_score, stress_score, regime["code"])
        stress_profile = _stress_profile(stress_score)

        history.append(
            {
                "date": row["date"],
                "close": round(close, 2),
                "regime_code": regime["code"],
                "regime_label": regime["label"],
                "bias": regime["bias"],
                "confidence": confidence,
                "direction_score": direction_score,
                "regime_score": direction_score,
                "stress_score": stress_score,
                "stress_label": stress_profile["stress_label"],
                "stress_tone": stress_profile["stress_tone"],
                "momentum_20": round(momentum_20 * 100, 2) if momentum_20 is not None else None,
                "momentum_90": round(momentum_90 * 100, 2) if momentum_90 is not None else None,
                "drawdown_ath": round(drawdown_ath * 100, 2) if drawdown_ath is not None else None,
                "close_vs_200": round(close_vs_200 * 100, 2) if close_vs_200 is not None else None,
            }
        )

        latest_metrics = metrics
        latest_direction_signals = direction_signals
        latest_stress_signals = stress_signals
        latest_regime = regime

    return history, latest_metrics, latest_direction_signals, latest_stress_signals, latest_regime


def build_regime_payload(rows):
    if not rows:
        return {
            "as_of": None,
            "price": None,
            "regime_code": "unknown",
            "regime_label": "Недостаточно данных",
            "bias": "neutral",
            "confidence": 0,
            "direction_score": 0,
            "regime_score": 0,
            "stress_score": 0,
            "stress_label": "Нет данных",
            "stress_tone": "neutral",
            "summary": "В таблице btc_daily нет данных для построения режима.",
            "direction_signals": [],
            "stress_signals": [],
            "signals": [],
            "metrics": {},
            "history": [],
        }

    history, latest_metrics, direction_signals, stress_signals, regime = calculate_regime_history(rows)
    latest_point = history[-1]
    stress_profile = _stress_profile(latest_point["stress_score"])
    summary = regime["summary"] + " " + stress_profile["stress_summary"]

    return {
        "as_of": latest_point["date"],
        "price": latest_point["close"],
        "regime_code": latest_point["regime_code"],
        "regime_label": latest_point["regime_label"],
        "bias": latest_point["bias"],
        "confidence": latest_point["confidence"],
        "direction_score": latest_point["direction_score"],
        "regime_score": latest_point["regime_score"],
        "stress_score": latest_point["stress_score"],
        "stress_label": latest_point["stress_label"],
        "stress_tone": latest_point["stress_tone"],
        "summary": summary,
        "direction_signals": direction_signals,
        "stress_signals": stress_signals,
        "signals": direction_signals + stress_signals,
        "metrics": {
            "momentum_20": latest_point["momentum_20"],
            "momentum_90": latest_point["momentum_90"],
            "drawdown_ath": latest_point["drawdown_ath"],
            "close_vs_200": latest_point["close_vs_200"],
        },
        "history": history[-540:],
    }
