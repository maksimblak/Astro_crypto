"""Market regime calculation for the BTC dashboard."""

from __future__ import annotations

from statistics import mean, median, pstdev


def _avg(values):
    return mean(values) if values else None


def _std(values):
    if len(values) < 2:
        return None
    return pstdev(values)


def _median(values):
    return median(values) if values else None


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


def _fmt_float(value, digits=2):
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def _fmt_index(value, digits=0):
    if value is None:
        return "—"
    return f"{value:.{digits}f}/100"


def _fmt_count(value):
    if value is None:
        return "—"
    return f"{value:,.0f}"


def _take(values, end_idx, window):
    start = max(0, end_idx - window + 1)
    return values[start : end_idx + 1]


def _row_value(row, key, default=None):
    if hasattr(row, "keys") and key in row.keys():
        return row[key]
    if isinstance(row, dict):
        return row.get(key, default)
    return default


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


def _context_signal(label, value, note, tone, available=True):
    return {
        "label": label,
        "value": value,
        "note": note,
        "tone": tone if tone in {"bull", "bear", "neutral"} else "neutral",
        "category": "context",
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
    if stress_score >= 6:
        return {
            "stress_label": "Капитуляция",
            "stress_tone": "bear",
            "stress_summary": "Stress extreme: волатильность и просадка уже сами стали отдельным фактором.",
        }
    if stress_score >= 4:
        return {
            "stress_label": "Высокий stress",
            "stress_tone": "bear",
            "stress_summary": "Stress высокий: движение может быть резким, но это не равнозначно направлению.",
        }
    if stress_score >= 2:
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


def _context_profile(context_score):
    if context_score >= 3:
        return {
            "context_label": "External tailwind",
            "context_tone": "bull",
            "context_summary": "Внешний слой поддерживает режим: attention, derivatives и on-chain не спорят с ростом.",
        }
    if context_score <= -3:
        return {
            "context_label": "External headwind",
            "context_tone": "bear",
            "context_summary": "Внешний слой добавляет risk-off: crowding и on-chain пока не улучшают картину.",
        }
    return {
        "context_label": "External neutral",
        "context_tone": "neutral",
        "context_summary": "Внешний слой без экстремума: sentiment, derivatives и on-chain сейчас скорее фон, чем триггер.",
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
    amihud_z = metrics["amihud_z_90d"]
    if amihud_z is None:
        amihud_points = 0
    elif amihud_z >= 1.5:
        amihud_points = 2
    elif amihud_z >= 0.75:
        amihud_points = 1
    else:
        amihud_points = 0

    range_compression = metrics["range_compression_20d"]
    if range_compression is None:
        range_points = 0
    elif range_compression >= 1.75:
        range_points = 2
    elif range_compression >= 1.35:
        range_points = 1
    else:
        range_points = 0

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
            "Amihud illiquidity (z)",
            _fmt_ratio(amihud_z),
            "Рост illiquidity значит, что рынок стал тоньше: те же ордера двигают цену сильнее.",
            amihud_points,
            amihud_z is not None,
        ),
        _stress_signal(
            "Range state 20д",
            _fmt_ratio(range_compression),
            "Диапазон относительно median 20д. Выше 1.35x = рынок уже разжат и хуже переносит шум.",
            range_points,
            range_compression is not None,
        ),
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
            "Импульсный stress 20д",
            _fmt_pct(mom20),
            "Резкий короткий спад добавляет stress, но не должен доминировать над 90-дневным трендом.",
            momentum_points,
            mom20 is not None,
        ),
    ]


def _build_context_signals(metrics, direction_score, stress_score):
    wiki_z = metrics["wiki_views_z_30d"]
    if wiki_z is None:
        wiki_tone = "neutral"
    elif wiki_z >= 2.0:
        wiki_tone = "bear"
    else:
        wiki_tone = "neutral"

    fear_greed = metrics["fear_greed_value"]
    if fear_greed is None:
        fear_tone = "neutral"
    elif fear_greed >= 75:
        fear_tone = "bear"
    elif fear_greed <= 20 and stress_score >= 2:
        fear_tone = "bull"
    else:
        fear_tone = "neutral"

    funding_z = metrics["funding_rate_z_30d"]
    if funding_z is None:
        funding_tone = "neutral"
    elif funding_z >= 1.5:
        funding_tone = "bear"
    elif funding_z <= -1.5:
        funding_tone = "bull"
    else:
        funding_tone = "neutral"

    perp_premium = metrics["perp_premium_daily"]
    perp_premium_z = metrics["perp_premium_z_30d"]
    if perp_premium is None and perp_premium_z is None:
        premium_tone = "neutral"
    elif perp_premium is not None and perp_premium <= -0.001:
        premium_tone = "bear"
    elif perp_premium_z is not None and perp_premium_z >= 1.5:
        premium_tone = "bear"
    elif perp_premium is not None and perp_premium > 0.0005 and direction_score > 0:
        premium_tone = "bull"
    else:
        premium_tone = "neutral"

    oi_z = metrics["open_interest_z_30d"]
    if oi_z is None:
        oi_tone = "neutral"
    elif oi_z >= 1.5:
        oi_tone = "bear"
    elif oi_z <= -1.0 and stress_score >= 2:
        oi_tone = "bull"
    else:
        oi_tone = "neutral"

    onchain_z = metrics["onchain_activity_z_30d"]
    if onchain_z is None:
        onchain_tone = "neutral"
    elif onchain_z >= 1.0:
        onchain_tone = "bull"
    elif onchain_z <= -1.0:
        onchain_tone = "bear"
    else:
        onchain_tone = "neutral"

    return [
        _context_signal(
            "Wikipedia attention",
            _fmt_float(wiki_z),
            "Сильный всплеск pageviews обычно означает crowd attention и поздний вход толпы, а не ранний edge.",
            wiki_tone,
            wiki_z is not None,
        ),
        _context_signal(
            "Fear & Greed",
            _fmt_index(fear_greed),
            "Extreme greed добавляет перегрев. Extreme fear полезен только как washout-контекст, а не как самостоятельный long.",
            fear_tone,
            fear_greed is not None,
        ),
        _context_signal(
            "Funding crowding",
            _fmt_float(funding_z),
            "Funding показывает перекос плеча. Высокий положительный funding чаще ухудшает reward/risk, чем подтверждает тренд.",
            funding_tone,
            funding_z is not None,
        ),
        _context_signal(
            "Perp premium",
            _fmt_pct(perp_premium, 2),
            "Премия perpetual к индексу помогает понять, поддерживает ли деривативный слой спот или уже перегрет.",
            premium_tone,
            perp_premium is not None or perp_premium_z is not None,
        ),
        _context_signal(
            "Open interest",
            _fmt_float(oi_z),
            "Высокий OI сам по себе не bearish, но в сочетании с трендом чаще означает crowding, а не безопасное продолжение.",
            oi_tone,
            oi_z is not None,
        ),
        _context_signal(
            "On-chain activity",
            _fmt_float(onchain_z),
            "Composite из active addresses и tx count. Это режимный фон сети, а не intraday trigger.",
            onchain_tone,
            onchain_z is not None,
        ),
    ]


def calculate_regime_history(rows):
    closes = [row["close"] for row in rows]
    highs = [row["high"] for row in rows]
    lows = [row["low"] for row in rows]
    volumes = [row["volume"] for row in rows]
    returns = []
    amihud_daily = []
    amihud_20_series = []
    amihud_z_90_series = []
    true_range_pct_series = []
    range_compression_series = []

    for idx, close in enumerate(closes):
        prev_close = closes[idx - 1] if idx > 0 else None
        daily_return = _pct_change(close, prev_close)
        returns.append(daily_return)

        dollar_volume = close * volumes[idx]
        daily_amihud = (
            abs(daily_return) / dollar_volume
            if daily_return is not None and dollar_volume not in (None, 0)
            else None
        )
        amihud_daily.append(daily_amihud)

        amihud_20 = _avg([value for value in _take(amihud_daily, idx, 20) if value is not None])
        amihud_20_series.append(amihud_20)

        amihud_window_90 = [value for value in _take(amihud_20_series, idx, 90) if value is not None]
        amihud_mean_90 = _avg(amihud_window_90)
        amihud_std_90 = _std(amihud_window_90)
        if amihud_20 is None or amihud_mean_90 is None or amihud_std_90 in (None, 0):
            amihud_z_90_series.append(None)
        else:
            amihud_z_90_series.append((amihud_20 - amihud_mean_90) / amihud_std_90)

        if prev_close is None:
            true_range = highs[idx] - lows[idx]
        else:
            true_range = max(
                highs[idx] - lows[idx],
                abs(highs[idx] - prev_close),
                abs(lows[idx] - prev_close),
            )
        true_range_pct = true_range / close if close not in (None, 0) else None
        true_range_pct_series.append(true_range_pct)

        range_baseline = _median([value for value in _take(true_range_pct_series, idx, 20) if value is not None])
        if true_range_pct is None or range_baseline in (None, 0):
            range_compression_series.append(None)
        else:
            range_compression_series.append(true_range_pct / range_baseline)

    history = []
    rolling_ath = 0.0
    latest_direction_signals = []
    latest_stress_signals = []
    latest_context_signals = []
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
            "date": _row_value(row, "date"),
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
            "amihud_illiquidity_20d": _row_value(row, "amihud_illiquidity_20d", amihud_20_series[idx]),
            "amihud_z_90d": _row_value(row, "amihud_z_90d", amihud_z_90_series[idx]),
            "range_compression_20d": _row_value(row, "range_compression_20d", range_compression_series[idx]),
            "wiki_views": _row_value(row, "wiki_views"),
            "wiki_views_7d": _row_value(row, "wiki_views_7d"),
            "wiki_views_z_30d": _row_value(row, "wiki_views_z_30d"),
            "fear_greed_value": _row_value(row, "fear_greed_value"),
            "fear_greed_z_30d": _row_value(row, "fear_greed_z_30d"),
            "funding_rate_daily": _row_value(row, "funding_rate_daily"),
            "funding_rate_z_30d": _row_value(row, "funding_rate_z_30d"),
            "perp_premium_daily": _row_value(row, "perp_premium_daily"),
            "perp_premium_z_30d": _row_value(row, "perp_premium_z_30d"),
            "open_interest_value": _row_value(row, "open_interest_value"),
            "open_interest_z_30d": _row_value(row, "open_interest_z_30d"),
            "unique_addresses": _row_value(row, "unique_addresses"),
            "unique_addresses_z_30d": _row_value(row, "unique_addresses_z_30d"),
            "tx_count": _row_value(row, "tx_count"),
            "tx_count_z_30d": _row_value(row, "tx_count_z_30d"),
            "onchain_activity_z_30d": _row_value(row, "onchain_activity_z_30d"),
        }

        direction_signals = _build_direction_signals(metrics)
        stress_signals = _build_stress_signals(metrics)
        direction_score = sum(signal["impact"] for signal in direction_signals)
        stress_score = sum(signal["points"] for signal in stress_signals)
        context_signals = _build_context_signals(metrics, direction_score, stress_score)
        context_score = sum(
            1 if signal["tone"] == "bull" else -1 if signal["tone"] == "bear" else 0
            for signal in context_signals
            if signal["available"]
        )

        regime = _classify_regime(metrics, direction_score, stress_score)
        confidence = _direction_confidence(direction_signals, direction_score, stress_score, regime["code"])
        stress_profile = _stress_profile(stress_score)
        context_profile = _context_profile(context_score)

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
                "context_score": context_score,
                "context_label": context_profile["context_label"],
                "context_tone": context_profile["context_tone"],
                "momentum_20": round(momentum_20 * 100, 2) if momentum_20 is not None else None,
                "momentum_90": round(momentum_90 * 100, 2) if momentum_90 is not None else None,
                "drawdown_ath": round(drawdown_ath * 100, 2) if drawdown_ath is not None else None,
                "close_vs_200": round(close_vs_200 * 100, 2) if close_vs_200 is not None else None,
                "amihud_z_90d": round(metrics["amihud_z_90d"], 2) if metrics["amihud_z_90d"] is not None else None,
                "range_compression_20d": round(metrics["range_compression_20d"], 2) if metrics["range_compression_20d"] is not None else None,
                "wiki_views_z_30d": round(metrics["wiki_views_z_30d"], 2) if metrics["wiki_views_z_30d"] is not None else None,
                "fear_greed_value": round(metrics["fear_greed_value"], 1) if metrics["fear_greed_value"] is not None else None,
                "funding_rate_z_30d": round(metrics["funding_rate_z_30d"], 2) if metrics["funding_rate_z_30d"] is not None else None,
                "perp_premium_daily": round(metrics["perp_premium_daily"] * 100, 3) if metrics["perp_premium_daily"] is not None else None,
                "perp_premium_z_30d": round(metrics["perp_premium_z_30d"], 2) if metrics["perp_premium_z_30d"] is not None else None,
                "open_interest_z_30d": round(metrics["open_interest_z_30d"], 2) if metrics["open_interest_z_30d"] is not None else None,
                "onchain_activity_z_30d": round(metrics["onchain_activity_z_30d"], 2) if metrics["onchain_activity_z_30d"] is not None else None,
            }
        )

        latest_direction_signals = direction_signals
        latest_stress_signals = stress_signals
        latest_context_signals = context_signals
        latest_regime = regime

    return history, latest_direction_signals, latest_stress_signals, latest_context_signals, latest_regime


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
            "context_score": 0,
            "context_label": "External neutral",
            "context_tone": "neutral",
            "summary": "В таблице btc_daily нет данных для построения режима.",
            "direction_signals": [],
            "stress_signals": [],
            "context_signals": [],
            "signals": [],
            "metrics": {},
            "history": [],
        }

    history, direction_signals, stress_signals, context_signals, regime = calculate_regime_history(rows)
    latest_point = history[-1]
    stress_profile = _stress_profile(latest_point["stress_score"])
    context_profile = _context_profile(latest_point["context_score"])
    summary = " ".join(
        [
            regime["summary"],
            stress_profile["stress_summary"],
            context_profile["context_summary"],
        ]
    )

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
        "context_score": latest_point["context_score"],
        "context_label": latest_point["context_label"],
        "context_tone": latest_point["context_tone"],
        "summary": summary,
        "direction_signals": direction_signals,
        "stress_signals": stress_signals,
        "context_signals": context_signals,
        "signals": direction_signals + stress_signals + context_signals,
        "metrics": {
            "momentum_20": latest_point["momentum_20"],
            "momentum_90": latest_point["momentum_90"],
            "drawdown_ath": latest_point["drawdown_ath"],
            "close_vs_200": latest_point["close_vs_200"],
            "amihud_z_90d": latest_point["amihud_z_90d"],
            "range_compression_20d": latest_point["range_compression_20d"],
            "wiki_views_z_30d": latest_point["wiki_views_z_30d"],
            "fear_greed_value": latest_point["fear_greed_value"],
            "funding_rate_z_30d": latest_point["funding_rate_z_30d"],
            "perp_premium_daily": latest_point["perp_premium_daily"],
            "perp_premium_z_30d": latest_point["perp_premium_z_30d"],
            "open_interest_z_30d": latest_point["open_interest_z_30d"],
            "onchain_activity_z_30d": latest_point["onchain_activity_z_30d"],
        },
        "history": history[-540:],
    }
