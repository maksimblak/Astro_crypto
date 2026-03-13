"""
Bitcoin Macro Cycle Top/Bottom Indicators — Reference & Implementation Guide
=============================================================================

Comprehensive research on data-backed on-chain indicators for identifying
Bitcoin macro cycle tops and bottoms. Each indicator includes:
- Formula / calculation method
- Historical signal accuracy
- Thresholds (top vs bottom)
- Free data sources / APIs

Compiled: 2026-03-13
"""

# ============================================================================
# FREE DATA SOURCES & APIs
# ============================================================================

FREE_DATA_SOURCES = {
    "bgeometrics": {
        "description": "Наиболее полный бесплатный API для on-chain метрик Bitcoin",
        "base_url": "https://bitcoin-data.com",
        "docs": "https://bitcoin-data.com/api/scalar.html",
        "auth": "Bearer token (бесплатная регистрация)",
        "rate_limit": "8 req/hour, 15 req/day (free tier)",
        "endpoints": {
            "mvrv": "/v1/mvrv",
            "nupl": "/v1/nupl",
            "sopr": "/v1/sopr",
            "puell_multiple": "/v1/puell-multiple",  # предполагаемый path
            "realized_cap": "/v1/realized-cap",
            "cdd": "/v1/cdd",
            "hashrate": "/v1/hashrate",
            "reserve_risk": "/v1/reserve-risk",
            "pi_cycle_top": "/v1/pi-cycle-top",
            "s2f": "/v1/s2f",
            "nvt": "/v1/nvt",
            "exchange_reserve": "/v1/exchange-reserve-btc",
            "exchange_inflow": "/v1/exchange-inflow",
            "exchange_outflow": "/v1/exchange-outflow",
            "supply_profit": "/v1/supply-profit",
            "supply_loss": "/v1/supply-loss",
            "hodl_waves": "/v1/hodl-waves",
            "technical_indicators": "/v1/technical-indicators",
        },
        "csv_export": "Добавить /csv к любому endpoint",
        "params": "?day=YYYY-MM-DD, ?startday=...&endday=..., ?page=...&size=...",
    },
    "coinmetrics_community": {
        "description": "Бесплатный API без ключа, Creative Commons лицензия",
        "base_url": "https://community-api.coinmetrics.io/v4",
        "docs": "https://docs.coinmetrics.io/api/v4/",
        "auth": "Не требуется для community endpoints",
        "rate_limit": "10 req / 6 sec, 10 параллельных запросов",
        "key_metrics": [
            "CapRealUSD",      # Realized Cap
            "CapMVRVCur",      # MVRV (current supply)
            "CapMVRVFF",       # MVRV (free float)
            "PriceUSD",        # BTC price
            "SplyCur",         # Current supply
            "TxTfrValAdjUSD",  # Transfer volume (adjusted)
            "NVTAdj",          # NVT adjusted
            "RevUSD",          # Miner revenue USD
            "HashRate",        # Network hashrate
        ],
        "example_url": (
            "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
            "?assets=btc&metrics=CapRealUSD,CapMVRVCur,PriceUSD"
            "&frequency=1d&start_time=2020-01-01"
        ),
    },
    "blockchain_com": {
        "description": "Базовые блокчейн-метрики, без аутентификации",
        "base_url": "https://api.blockchain.info",
        "charts_url": "https://api.blockchain.info/charts/{name}?timespan=all&format=json",
        "available_charts": [
            "market-cap",
            "trade-volume",
            "hash-rate",
            "difficulty",
            "miners-revenue",
            "transaction-fees",
            "n-transactions",
            "n-unique-addresses",
            "nvt",              # NVT ratio
            "mvrv",             # MVRV
        ],
    },
    "coingecko": {
        "description": "Ценовые данные и базовые метрики, 100 req/min",
        "base_url": "https://api.coingecko.com/api/v3",
        "auth": "Не требуется (demo key для повышенных лимитов)",
        "key_endpoints": [
            "/coins/bitcoin/market_chart?vs_currency=usd&days=max",
            "/coins/bitcoin/ohlc?vs_currency=usd&days=max",
        ],
    },
    "glassnode_free": {
        "description": "Tier 1 метрики, daily resolution, с задержкой",
        "base_url": "https://api.glassnode.com/v1/metrics",
        "auth": "API key (бесплатная регистрация)",
        "note": "Большинство on-chain метрик требуют платной подписки. "
                "Free tier = очень ограниченный набор.",
    },
    "alternative_charts": {
        "description": "Визуализация без API, но с полезными данными",
        "sites": [
            "https://charts.bitbo.io",            # ~50 бесплатных чартов
            "https://www.bitcoinmagazinepro.com/charts/",
            "https://charts.checkonchain.com/",
            "https://newhedge.io/bitcoin",
            "https://charts.bgeometrics.com/",
            "https://hodlwave.com/",               # HODL Waves
        ],
    },
}


# ============================================================================
# INDICATOR DEFINITIONS
# ============================================================================

INDICATORS = {}

# ---------------------------------------------------------------------------
# 1. MVRV Z-Score
# ---------------------------------------------------------------------------
INDICATORS["mvrv_zscore"] = {
    "name": "MVRV Z-Score",
    "category": "valuation",
    "creator": "Murad Mahmudov & David Puell (2018)",
    "description": (
        "Измеряет стандартное отклонение Market Cap от Realized Cap. "
        "Показывает насколько текущая рыночная оценка отклоняется от "
        "агрегированной себестоимости всех монет."
    ),
    "formula": {
        "MVRV_Ratio": "Market Cap / Realized Cap",
        "MVRV_Z_Score": "(Market Cap - Realized Cap) / StdDev(Market Cap)",
        "Market_Cap": "Current Price × Circulating Supply",
        "Realized_Cap": "Σ(UTXO_value × price_when_UTXO_last_moved) для всех UTXO",
    },
    "thresholds": {
        "extreme_top": {"mvrv_z": "> 7", "mvrv_ratio": "> 3.7", "signal": "SELL — эйфория, macro top"},
        "overheated":  {"mvrv_z": "5-7", "mvrv_ratio": "2.5-3.7", "signal": "CAUTION — перегрев"},
        "fair_value":  {"mvrv_z": "0-3", "mvrv_ratio": "1.0-2.5", "signal": "HOLD — нормальная оценка"},
        "undervalued": {"mvrv_z": "< 0", "mvrv_ratio": "< 1.0", "signal": "BUY — рынок ниже себестоимости"},
    },
    "historical_signals": {
        "2011_top": "MVRV Z > 9, BTC $31 → пик с точностью ~1 неделя",
        "2013_top": "MVRV Z > 8, BTC $1,150 → пик с точностью ~2 недели",
        "2017_top": "MVRV Z > 7, BTC $19,700 → пик с точностью ~2 недели",
        "2021_top": "MVRV Z ~7.5 в апреле (BTC $64K), не достиг красной зоны в ноябре",
        "2015_bottom": "MVRV Z < 0, BTC $200",
        "2018_bottom": "MVRV Z < 0, BTC $3,200",
        "2022_bottom": "MVRV Z < 0, BTC $15,500",
    },
    "accuracy": "Исторически сигнализировал macro top с точностью до 2 недель в 2011-2017. "
                "В 2021 цикле пиковые значения были ниже — признак diminishing returns.",
    "note": "С каждым циклом пиковое значение Z-Score снижается. "
            "Ожидать Z > 7 может быть нереалистично для будущих циклов.",
    "data_sources": [
        "CoinMetrics: CapMVRVCur, CapMVRVFF",
        "BGeometrics: /v1/mvrv",
        "Blockchain.com: /charts/mvrv",
    ],
}

# ---------------------------------------------------------------------------
# 2. NUPL (Net Unrealized Profit/Loss)
# ---------------------------------------------------------------------------
INDICATORS["nupl"] = {
    "name": "NUPL — Net Unrealized Profit/Loss",
    "category": "valuation",
    "creator": "Adamant Capital / Tuur Demeester (2019)",
    "description": (
        "Показывает какая доля рыночной капитализации состоит из нереализованной "
        "прибыли. Определяет эмоциональную фазу рынка."
    ),
    "formula": {
        "NUPL": "(Market Cap - Realized Cap) / Market Cap",
        "alternative": "NUPL = 1 - (Realized Cap / Market Cap)",
        "range": "от -1 (полный убыток) до +1 (полная прибыль)",
    },
    "thresholds": {
        "euphoria":     {"range": "> 0.75",     "color": "красный",  "signal": "SELL — macro top, жадность"},
        "belief":       {"range": "0.50 – 0.75", "color": "оранжевый", "signal": "CAUTION — Is this a bubble?"},
        "optimism":     {"range": "0.25 – 0.50", "color": "жёлтый",  "signal": "HOLD — бычий тренд"},
        "hope_fear":    {"range": "0.00 – 0.25", "color": "зелёный", "signal": "ACCUMULATE"},
        "capitulation": {"range": "< 0.00",      "color": "синий",   "signal": "BUY — macro bottom, капитуляция"},
    },
    "historical_signals": {
        "2011_top": "NUPL > 0.90",
        "2013_top": "NUPL > 0.80",
        "2017_top": "NUPL > 0.76 (20 Dec 2017)",
        "2021_top": "NUPL достиг ~0.75 в апреле, ~0.68 в ноябре (не дошёл до эйфории)",
        "2015_bottom": "NUPL < 0 (капитуляция)",
        "2018_bottom": "NUPL < 0 (капитуляция)",
        "2022_bottom": "NUPL < 0 (капитуляция, BTC ~$15.5K)",
    },
    "accuracy": "5/5 macro tops совпали с NUPL > 0.75. Все macro bottoms совпали с NUPL < 0. "
                "В 2021 ноябрьский пик не достиг 0.75 — indicator сработал как warning.",
    "data_sources": [
        "BGeometrics: /v1/nupl",
        "CoinGlass, CryptoQuant, Glassnode (платно)",
    ],
}

# ---------------------------------------------------------------------------
# 3. Puell Multiple
# ---------------------------------------------------------------------------
INDICATORS["puell_multiple"] = {
    "name": "Puell Multiple",
    "category": "miner",
    "creator": "David Puell",
    "description": (
        "Сравнивает дневной доход майнеров (USD) с 365-дневной скользящей средней "
        "дохода. Отражает давление продажи со стороны майнеров."
    ),
    "formula": {
        "Puell_Multiple": "Daily Miner Revenue (USD) / MA365(Daily Miner Revenue (USD))",
        "Daily_Miner_Revenue": "Block Subsidy × BTC Price + Transaction Fees (USD)",
    },
    "thresholds": {
        "extreme_top":    {"value": "> 4.0",     "signal": "SELL — сильный перегрев, macro top"},
        "overheated":     {"value": "3.0 – 4.0", "signal": "CAUTION — зона распределения"},
        "fair":           {"value": "0.5 – 3.0", "signal": "HOLD — нормальный диапазон"},
        "undervalued":    {"value": "< 0.5",     "signal": "BUY — macro bottom, капитуляция майнеров"},
    },
    "historical_signals": {
        "2013_top":   "Puell > 6 → macro top",
        "2017_top":   "Puell > 4 → macro top",
        "2021_top":   "Puell ~3.5 в апреле (diminishing returns)",
        "2015_bottom": "Puell < 0.3 → отличная точка входа",
        "2018_bottom": "Puell < 0.3 → macro bottom",
        "2022_bottom": "Puell < 0.4 → bottom zone",
        "note": "После каждого halving Puell временно падает (доход падает в 2x), "
                "это НЕ bottom signal — нужно отличать от органической капитуляции.",
    },
    "accuracy": "Работал в каждом цикле. Пиковые значения снижаются: 8+ → 6 → 4 → 3.5. "
                "Для bottom: < 0.5 = 100% hit rate по macro bottoms.",
    "data_sources": [
        "BGeometrics: /v1/puell-multiple (предполагаемый)",
        "CryptoQuant: /asset/btc/chart/network-indicator/puell-multiple",
        "CoinMetrics: RevUSD + MA365 для самостоятельного расчёта",
    ],
}

# ---------------------------------------------------------------------------
# 4. Reserve Risk
# ---------------------------------------------------------------------------
INDICATORS["reserve_risk"] = {
    "name": "Reserve Risk",
    "category": "holder_behavior",
    "creator": "Hans Hauge",
    "description": (
        "Отношение текущей цены (стимул продавать) к HODL Bank (кумулятивная "
        "неиспользованная opportunity cost). Измеряет уверенность hodlers "
        "относительно текущей цены."
    ),
    "formula": {
        "Reserve_Risk": "Price / HODL Bank",
        "HODL_Bank": "Cumulative sum of (Unspent Coin Days × BTC Supply)",
        "concept": (
            "Когда уверенность высока а цена низкая → Reserve Risk низкий (хорошее время покупать). "
            "Когда уверенность падает а цена высока → Reserve Risk высокий (хорошее время продавать)."
        ),
    },
    "thresholds": {
        "extreme_top": {"value": "> 0.02",     "signal": "SELL — macro blow-off top"},
        "overheated":  {"value": "0.008 – 0.02", "signal": "CAUTION — перегрев"},
        "fair":        {"value": "0.0026 – 0.008", "signal": "HOLD"},
        "undervalued": {"value": "< 0.0026",   "signal": "BUY — зона накопления"},
    },
    "historical_signals": {
        "tops": "Значения > 0.02 появляются только кратковременно на blow-off tops — каждый раз работало",
        "bottoms": "Значения < 0.0026 совпадали со всеми macro bottoms",
        "2022": "Reserve Risk упал ниже 0.001 — исторический минимум, идеальная точка входа",
    },
    "accuracy": "Один из самых надёжных индикаторов для macro bottoms. "
                "Для tops менее точен по времени, но зона > 0.02 = 100% hit rate.",
    "data_sources": [
        "BGeometrics: /v1/reserve-risk",
        "Glassnode (платно)",
        "CryptoQuant",
    ],
}

# ---------------------------------------------------------------------------
# 5. RHODL Ratio
# ---------------------------------------------------------------------------
INDICATORS["rhodl_ratio"] = {
    "name": "RHODL Ratio — Realized HODL Ratio",
    "category": "holder_behavior",
    "creator": "Philip Swift",
    "description": (
        "Соотношение Realized Value монет возрастом 1 неделю к Realized Value "
        "монет возрастом 1-2 года. Корректируется на возраст рынка. "
        "Измеряет баланс между спекулятивным и долгосрочным капиталом."
    ),
    "formula": {
        "RHODL_Ratio": "(RV_1week_band / RV_1to2year_band) × Market_Age_Days",
        "RV_band": "Σ(UTXO_value × price_at_creation) для монет в данном возрастном диапазоне",
        "Market_Age_Days": "Дней с Genesis Block (коррекция на рост HODLing и потерянные монеты)",
    },
    "thresholds": {
        "extreme_top": {"value": "> 50000", "signal": "SELL — красная зона, macro top"},
        "overheated":  {"value": "10000 – 50000", "signal": "CAUTION — распределение"},
        "fair":        {"value": "1000 – 10000", "signal": "HOLD"},
        "undervalued": {"value": "< 1000", "signal": "BUY — зелёная зона"},
    },
    "historical_signals": {
        "2013_top": "RHODL в красной зоне → macro top",
        "2017_top": "RHODL в красной зоне → macro top",
        "2021_top": "RHODL приблизился к красной зоне в апреле, не достиг в ноябре",
    },
    "accuracy": "Работал во всех циклах. Красная зона = 100% hit rate для tops.",
    "data_sources": [
        "BitcoinMagazinePro: /charts/rhodl-ratio/",
        "Newhedge: /bitcoin/realized-hodl-ratio",
    ],
}

# ---------------------------------------------------------------------------
# 6. Pi Cycle Top Indicator
# ---------------------------------------------------------------------------
INDICATORS["pi_cycle_top"] = {
    "name": "Pi Cycle Top Indicator",
    "category": "technical_onchain",
    "creator": "Philip Swift",
    "description": (
        "Пересечение 111-дневной MA и 2× 350-дневной MA. "
        "Название связано с тем что 350/111 ≈ π (3.153)."
    ),
    "formula": {
        "Short_MA": "SMA(Price, 111)",
        "Long_MA": "SMA(Price, 350) × 2",
        "Signal": "TOP когда Short_MA пересекает Long_MA снизу вверх",
    },
    "thresholds": {
        "top_signal": "111DMA crosses above 350DMA × 2 → SELL",
        "note": "Бинарный индикатор — либо есть пересечение, либо нет",
    },
    "historical_signals": {
        "2013_nov_top":  "Сигнал 3 Dec 2013, пик 4 Dec 2013 → точность 1 ДЕНЬ, затем -86%",
        "2017_top":      "Сигнал 16 Dec 2017, пик 17 Dec 2017 → точность 1 ДЕНЬ, затем -84%",
        "2021_apr_top":  "Сигнал 12 Apr 2021, пик 14 Apr 2021 → точность 2 ДНЯ, затем -53%",
        "2021_nov_top":  "НЕ СРАБОТАЛ — пик $69K без пересечения MA",
    },
    "accuracy": (
        "85% historical accuracy. В 3 из 4 macro tops — с точностью 1-2 дня. "
        "Провал: не поймал ноябрь 2021 ($69K). "
        "Это единственный индикатор с точностью до ДНЕЙ для tops."
    ),
    "limitations": "Только для tops. Не даёт bottom signals. Не сработал в 2021 ноябре.",
    "data_sources": [
        "BGeometrics: /v1/pi-cycle-top",
        "Можно рассчитать самостоятельно: SMA(111) и SMA(350)×2 от ценовых данных",
    ],
}

# ---------------------------------------------------------------------------
# 7. Hash Ribbons
# ---------------------------------------------------------------------------
INDICATORS["hash_ribbons"] = {
    "name": "Hash Ribbons",
    "category": "miner",
    "creator": "Charles Edwards (Capriole Investments)",
    "description": (
        "Пересечение 30-дневной и 60-дневной SMA хешрейта. "
        "Определяет периоды капитуляции и восстановления майнеров."
    ),
    "formula": {
        "Short_MA": "SMA(Hashrate, 30)",
        "Long_MA": "SMA(Hashrate, 60)",
        "Capitulation": "30DMA < 60DMA (хешрейт падает → майнеры выключаются)",
        "Recovery": "30DMA > 60DMA (хешрейт восстанавливается)",
        "Buy_Signal": "Recovery + 10DMA(Price) > 20DMA(Price)",
    },
    "thresholds": {
        "capitulation": "30DMA hashrate пересекает 60DMA вниз → MINER STRESS",
        "buy_signal": "Обратное пересечение вверх + цена > 10/20 SMA → BUY (blue dot)",
    },
    "historical_signals": {
        "total_signals": "14 buy signals с 2013 года",
        "win_rate": "64.29% profitable (по 253 дня средняя длительность)",
        "avg_return": ">5000% к следующему cycle peak",
        "max_drawdown": "-15% от точки входа",
        "2022_signal": "Buy signal после FTX collapse → BTC ~$16K, затем рост до $126K",
    },
    "accuracy": "Один из лучших bottom indicators. Средний return >5000% к следующему пику. "
                "Может давать ложные сигналы mid-cycle (как в мае/июле 2025).",
    "data_sources": [
        "BGeometrics: /v1/hashrate + самостоятельный расчёт SMA",
        "CoinMetrics: HashRate",
        "TradingView: скрипт Hash Ribbons by capriole_charles",
    ],
}

# ---------------------------------------------------------------------------
# 8. SOPR (Spent Output Profit Ratio)
# ---------------------------------------------------------------------------
INDICATORS["sopr"] = {
    "name": "SOPR — Spent Output Profit Ratio",
    "category": "valuation",
    "creator": "Renato Shirakashi",
    "description": (
        "Отношение цены продажи к цене покупки для всех перемещённых монет. "
        "Показывает реализуют ли участники рынка прибыль или убыток."
    ),
    "formula": {
        "SOPR": "Σ(UTXO_value_at_spent_time) / Σ(UTXO_value_at_creation_time)",
        "simplified": "Price Sold / Price Paid (агрегировано по всем UTXO за день)",
        "STH_SOPR": "SOPR только для UTXO моложе 155 дней",
        "LTH_SOPR": "SOPR только для UTXO старше 155 дней",
    },
    "thresholds": {
        "top_zone":   {"value": ">> 1 (e.g. > 1.05 sustained)", "signal": "Массовая фиксация прибыли"},
        "neutral":    {"value": "≈ 1.0", "signal": "Breakeven — ключевой уровень поддержки в bull market"},
        "bottom_zone": {"value": "< 1.0 (sustained)", "signal": "Капитуляция — продажа в убыток"},
    },
    "key_patterns": {
        "bull_support": "В bull market SOPR = 1.0 работает как поддержка (люди не продают в убыток)",
        "bear_resistance": "В bear market SOPR = 1.0 работает как сопротивление (продают при breakeven)",
        "capitulation": "Устойчивый SOPR < 1.0 = macro bottom forming",
    },
    "accuracy": "Хорошо работает в комбинации с другими индикаторами. "
                "STH-SOPR < 1.0 = коррекция в bull market, LTH-SOPR < 1.0 = full capitulation.",
    "data_sources": [
        "BGeometrics: /v1/sopr",
        "CryptoQuant: /asset/btc/chart/market-indicator/spent-output-profit-ratio-sopr",
        "Glassnode (платно)",
    ],
}

# ---------------------------------------------------------------------------
# 9. Stock-to-Flow (S2F)
# ---------------------------------------------------------------------------
INDICATORS["stock_to_flow"] = {
    "name": "Stock-to-Flow (S2F)",
    "category": "supply_model",
    "creator": "PlanB (2019)",
    "status": "BROKEN / INVALIDATED",
    "description": (
        "Модель основана на отношении существующего запаса (stock) к годовому "
        "притоку нового предложения (flow). Предсказывала что halving → рост цены "
        "по степенному закону."
    ),
    "formula": {
        "S2F_Ratio": "Current Supply / Annual Production",
        "Model_Price": "exp(-1.84) × S2F^3.36",
        "post_2024_halving_S2F": "~120 (аналогично золоту)",
    },
    "status_2026": {
        "verdict": "Статистически невалидна. Модель предсказывала $500K+ к 2025. "
                   "Реальная цена: $90-126K. Погрешность 4-5x.",
        "2022_failure": "Предсказывала >$100K, реальность: $16K (6x ниже)",
        "2024_halving": "Предсказывала $500K+, реальность: пик $126K (4x ниже)",
        "conclusion": "Полезна как framework (scarcity matters), но НЕ как ценовая модель. "
                      "Игнорирует спрос, макро, регуляции.",
    },
    "data_sources": [
        "BGeometrics: /v1/s2f",
        "BitcoinMagazinePro: /charts/stock-to-flow-model/",
    ],
}

# ---------------------------------------------------------------------------
# 10. Power Law Model
# ---------------------------------------------------------------------------
INDICATORS["power_law"] = {
    "name": "Bitcoin Power Law",
    "category": "supply_model",
    "creator": "Giovanni Santostasi (2024, refined Harold Christopher Burger 2019)",
    "status": "ACTIVE — наиболее точная долгосрочная модель на данный момент",
    "description": (
        "Цена Bitcoin следует степенному закону относительно времени. "
        "На log-log шкале ценовая траектория = прямая линия."
    ),
    "formula": {
        "core": "Price = A × (days_since_genesis)^n",
        "coefficients_v1": "Price = 1.0117e-17 × days^5.82",
        "coefficients_v2": "Price = 10^(-1.8478) × (days/365.25)^5.6163",
        "log_form": "log10(Price) = -17 + 5.82 × log10(days)",
        "R_squared": "95.65% на daily closes",
    },
    "bands": {
        "method": "Percentile bands от regression line",
        "upper_95": "97.5th percentile = cycle top zone",
        "lower_95": "2.5th percentile = cycle bottom zone",
        "upper_67": "83.5th percentile = overbought",
        "lower_67": "16.5th percentile = oversold",
    },
    "projections_2026": {
        "fair_value_2026": "~$100-150K (regression line)",
        "cycle_peak": "~$210K (Santostasi projection, Jan 2026)",
        "cycle_bottom": "~$60K (post-peak 2026)",
    },
    "accuracy": "R² > 95%. Предсказала $100K к Jan 2025 — сбылось. "
                "Наиболее живучая модель на данный момент. "
                "Но 10,000th day (May 2036) = $1M, что пока не проверяемо.",
    "limitations": "Игнорирует supply-side (halvings), спрос, макро. "
                   "Прошлые данные не гарантируют будущее.",
    "data_sources": [
        "Самостоятельный расчёт: нужны только дневные цены BTC",
        "https://charts.bitbo.io/long-term-power-law/",
        "https://bitcoinpower.law/",
        "https://www.porkopolis.io/thechart/",
    ],
}

# ---------------------------------------------------------------------------
# 11. Rainbow Chart
# ---------------------------------------------------------------------------
INDICATORS["rainbow_chart"] = {
    "name": "Bitcoin Rainbow Chart",
    "category": "supply_model",
    "creator": "Trolololo (BitcoinTalk, 2014)",
    "description": (
        "Логарифмическая регрессия с 9 цветными полосами сентимента. "
        "Визуальный macro-level инструмент."
    ),
    "formula": {
        "original_2014": "10^(3.109106 × ln(weeks_since_2009_01_09) - 8.164198)",
        "updated_2017": "10^(2.66167 × ln(days_since_2009_01_09) - 17.9184)",
        "latest": "log10(price) = 2.6521 × LN(days) - 18.163",
        "bands": "Множители выше и ниже центральной regression line",
        "calibration_points": "28-Nov-2012 $12.33, 9-Jul-2016 $651.94, 11-May-2020 $8,591.65",
    },
    "bands_top_to_bottom": [
        {"band": 9, "color": "Тёмно-красный", "label": "Maximum Bubble Territory"},
        {"band": 8, "color": "Красный",        "label": "Sell. Seriously, SELL!"},
        {"band": 7, "color": "Тёмно-оранжевый", "label": "FOMO Intensifies"},
        {"band": 6, "color": "Оранжевый",      "label": "Is This a Bubble?"},
        {"band": 5, "color": "Жёлтый",         "label": "HODL!"},
        {"band": 4, "color": "Светло-зелёный", "label": "Still Cheap"},
        {"band": 3, "color": "Зелёный",        "label": "Accumulate"},
        {"band": 2, "color": "Голубой",         "label": "BUY!"},
        {"band": 1, "color": "Синий",           "label": "Basically a Fire Sale"},
    ],
    "accuracy": "Macro framework — не точный индикатор. Полезен для общей ориентации по циклу.",
    "data_sources": [
        "https://charts.bitbo.io/rainbow/",
        "Самостоятельный расчёт: log regression + multiplier bands",
    ],
}

# ---------------------------------------------------------------------------
# 12. Thermocap Multiple
# ---------------------------------------------------------------------------
INDICATORS["thermocap"] = {
    "name": "Thermocap Multiple",
    "category": "miner",
    "creator": "Nic Carter",
    "description": (
        "Отношение Market Cap к Thermocap (кумулятивный доход майнеров за всю историю). "
        "Показывает сколько спекулятивной premium заложено в цену."
    ),
    "formula": {
        "Thermocap": "Σ(Block Subsidy × Price_at_block_time + Tx Fees) за все блоки",
        "Thermocap_Multiple": "Market Cap / Thermocap",
        "simplified": "Price / (Cumulative Miner Revenue / Supply) × scaling_factor",
    },
    "thresholds": {
        "extreme_top": {"value": "> 32-64x", "signal": "SELL — macro blow-off top"},
        "overheated":  {"value": "16-32x",   "signal": "CAUTION"},
        "fair":        {"value": "4-16x",    "signal": "HOLD"},
        "undervalued": {"value": "< 4x",     "signal": "BUY — macro bottom"},
        "raw_values": {
            "top": "> 0.000004 (4e-6)",
            "bottom": "< 0.0000004 (4e-7)",
        },
    },
    "accuracy": "Хороший macro framework. Совпадает со всеми историческими tops и bottoms.",
    "data_sources": [
        "CryptoQuant: /asset/btc/chart/market-data/thermo-cap",
        "Расчёт через CoinMetrics: RevUSD (cumulative) + Market Cap",
    ],
}

# ---------------------------------------------------------------------------
# 13. HODL Waves & 1yr+ HODL Wave
# ---------------------------------------------------------------------------
INDICATORS["hodl_waves"] = {
    "name": "HODL Waves / 1yr+ HODL Wave",
    "category": "holder_behavior",
    "creator": "Unchained Capital (2018, based on jratcliff UTXO work)",
    "description": (
        "Распределение supply по возрасту UTXO. 1yr+ HODL Wave показывает "
        "% supply который не двигался более года."
    ),
    "formula": {
        "HODL_Wave": "% of total supply in each age band (1d, 1w, 1m, 3m, 6m, 1y, 2y, 3y, 5y, 10y+)",
        "1yr_plus": "% supply с последним перемещением > 1 года назад",
    },
    "cycle_pattern": {
        "accumulation": "1yr+ HODL Wave растёт → smart money накапливает, цена на дне",
        "distribution": "1yr+ HODL Wave падает → старые монеты продаются на росте",
        "top_signal": "1yr+ HODL Wave минимум → максимальная распределение → macro top рядом",
        "bottom_signal": "1yr+ HODL Wave максимум → максимальное накопление → macro bottom",
    },
    "historical_thresholds": {
        "1yr_plus_at_tops": "~40-45% (минимум HODL waves)",
        "1yr_plus_at_bottoms": "~65-70% (максимум HODL waves)",
    },
    "accuracy": "Работал во всех циклах. Lag 3-6 месяцев — скорее confirming indicator.",
    "data_sources": [
        "BGeometrics: /v1/hodl-waves",
        "https://hodlwave.com/",
        "Glassnode (платно)",
    ],
}

# ---------------------------------------------------------------------------
# 14. Coin Days Destroyed (CDD)
# ---------------------------------------------------------------------------
INDICATORS["cdd"] = {
    "name": "Coin Days Destroyed (CDD)",
    "category": "holder_behavior",
    "creator": "Bitcoin community",
    "description": (
        "Метрика взвешивающая перемещение монет по их возрасту. "
        "Высокие значения = старые монеты двигаются (smart money продаёт)."
    ),
    "formula": {
        "CDD": "Σ(UTXO_amount × days_since_UTXO_created) для всех spent UTXO за день",
        "Supply_Adjusted_CDD": "CDD / Current Supply",
        "Binary_CDD": "1 если CDD > median(CDD), иначе 0",
        "VDD_Multiple": "CDD / MA365(CDD) — Value Days Destroyed Multiple",
    },
    "interpretation": {
        "high_CDD": "Старые монеты двигаются → часто совпадает с tops (distribution)",
        "low_CDD": "Старые монеты спят → accumulation phase",
        "spike": "Единовременный spike CDD может быть exchange cold wallet movement (ложный сигнал)",
    },
    "accuracy": "Хороший confirming indicator. Лучше использовать Supply-Adjusted CDD "
                "или Binary CDD для фильтрации шума.",
    "data_sources": [
        "BGeometrics: /v1/cdd",
        "CryptoQuant: /asset/btc/chart/network-indicator/coin-days-destroyed-cdd",
        "Glassnode: /metrics/indicators/Cdd",
    ],
}

# ---------------------------------------------------------------------------
# 15. NVT Ratio / NVT Signal
# ---------------------------------------------------------------------------
INDICATORS["nvt"] = {
    "name": "NVT Ratio / NVT Signal",
    "category": "valuation",
    "creator": "Willy Woo (NVT), Dmitry Kalichkin (NVTS)",
    "description": (
        'Network Value to Transactions — "P/E ratio для Bitcoin". '
        "Сравнивает рыночную оценку с реальным использованием сети."
    ),
    "formula": {
        "NVT_Ratio": "Market Cap / Daily Transaction Volume (USD)",
        "NVT_Signal": "Market Cap / MA90(Daily Transaction Volume (USD))",
    },
    "thresholds": {
        "overvalued": {"value": "NVT > 95 (или NVTS > 150)", "signal": "Сеть переоценена"},
        "fair":       {"value": "NVT 30-95",                 "signal": "Нормальная оценка"},
        "undervalued": {"value": "NVT < 30 (или NVTS < 50)", "signal": "Сеть недооценена"},
    },
    "limitations": "Не учитывает off-chain транзакции (Lightning, exchanges). "
                   "В 2024+ менее надёжен из-за Ordinals/Inscriptions искажающих volume.",
    "data_sources": [
        "BGeometrics: /v1/nvt",
        "Blockchain.com: /charts/nvt",
        "CoinMetrics: NVTAdj",
    ],
}

# ---------------------------------------------------------------------------
# 16. Exchange Reserves & Netflow
# ---------------------------------------------------------------------------
INDICATORS["exchange_metrics"] = {
    "name": "Exchange Reserves / Netflow / Whale Ratio",
    "category": "exchange",
    "description": (
        "Отслеживание потоков BTC на/с бирж. Рост резервов = давление продажи. "
        "Снижение = накопление."
    ),
    "formula": {
        "Exchange_Reserve": "Σ(BTC balances) на известных exchange addresses",
        "Netflow": "Exchange Inflow - Exchange Outflow (за период)",
        "Whale_Ratio": "Top-10 inflow volume / Total inflow volume",
    },
    "interpretation": {
        "declining_reserves": "BTC уходит с бирж → accumulation → bullish",
        "rising_reserves": "BTC приходит на биржи → готовятся продавать → bearish",
        "whale_ratio_high": "> 0.85 (85%) → киты доминируют в deposits → предшествует коррекции 30%+",
        "whale_ratio_low": "< 0.70 (70%) → organic accumulation → bullish",
    },
    "2025_context": {
        "whale_deposits": "64% всех exchange deposits по объёму = whale ratio 0.64 (Oct 2025)",
        "pattern": "Sustained outflows = bullish, spike inflows = distribution/selling",
    },
    "accuracy": "Хороший real-time sentiment indicator. Whale ratio > 85% = 30%+ drawdown в 2024-2025.",
    "data_sources": [
        "BGeometrics: /v1/exchange-reserve-btc, /v1/exchange-inflow, /v1/exchange-outflow",
        "CryptoQuant: exchange-flows, exchange-whale-ratio (наиболее полные данные)",
    ],
}


# ============================================================================
# COMPOSITE SCORING SYSTEM — рекомендация
# ============================================================================

COMPOSITE_SYSTEM = {
    "description": (
        "Ни один индикатор не работает в 100% случаев. Рекомендуется composite "
        "scoring system где каждый индикатор голосует TOP / BOTTOM / NEUTRAL."
    ),
    "top_indicators": {
        "primary": [
            {"name": "MVRV Z-Score", "weight": 0.20, "threshold": "> 6 = TOP, < 0 = BOTTOM"},
            {"name": "NUPL",         "weight": 0.20, "threshold": "> 0.75 = TOP, < 0 = BOTTOM"},
            {"name": "Pi Cycle Top", "weight": 0.15, "threshold": "Cross = TOP (бинарный)"},
        ],
        "secondary": [
            {"name": "Puell Multiple",  "weight": 0.10, "threshold": "> 4 = TOP, < 0.5 = BOTTOM"},
            {"name": "Reserve Risk",    "weight": 0.10, "threshold": "> 0.02 = TOP, < 0.0026 = BOTTOM"},
            {"name": "RHODL Ratio",     "weight": 0.10, "threshold": "Red zone = TOP"},
        ],
        "confirming": [
            {"name": "Exchange Netflow", "weight": 0.05, "threshold": "Sustained inflow = TOP"},
            {"name": "1yr+ HODL Wave",  "weight": 0.05, "threshold": "< 45% = TOP, > 65% = BOTTOM"},
            {"name": "Hash Ribbons",    "weight": 0.05, "threshold": "Buy signal = BOTTOM"},
        ],
    },
    "scoring": {
        "method": "Weighted sum: каждый индикатор = weight × signal (-1 BOTTOM, 0 NEUTRAL, +1 TOP)",
        "sell_threshold": "Composite Score > 0.6 = сильный SELL signal",
        "buy_threshold": "Composite Score < -0.6 = сильный BUY signal",
    },
    "diminishing_returns_adjustment": (
        "ВАЖНО: с каждым циклом пиковые значения MVRV, Puell, RHODL снижаются. "
        "Thresholds нужно пересматривать каждый цикл. "
        "2013: MVRV Z > 8+, 2017: MVRV Z > 7, 2021: MVRV Z ~5-6, 2025+: возможно 4-5."
    ),
    "cycle_2025_2026_context": {
        "peak": "$126K в Oct 2025 (ATH)",
        "current_decline": "~46% от ATH к Mar 2026",
        "4yr_cycle_status": "Впервые post-halving год (2025) закрылся в минусе",
        "theory": "Cycle может удлиняться / сглаживаться из-за институционализации (ETF, etc)",
    },
}


# ============================================================================
# IMPLEMENTATION NOTES
# ============================================================================

IMPLEMENTATION_NOTES = """
## Рекомендации для production system

### Приоритет источников данных (бесплатные):
1. BGeometrics API (bitcoin-data.com) — наиболее полный набор on-chain метрик
2. CoinMetrics Community API — без ключа, хорошие базовые метрики
3. Blockchain.com Charts API — MVRV, NVT, базовые
4. CoinGecko — ценовые данные, OHLCV
5. Самостоятельный расчёт — Pi Cycle, Power Law, Rainbow (нужны только цены)

### Метрики которые можно рассчитать из ценовых данных:
- Pi Cycle Top: SMA(111) и SMA(350)×2
- Power Law: regression на log-log scale
- Rainbow Chart: log regression + bands
- Mayer Multiple: Price / SMA(200)

### Метрики требующие on-chain данных:
- MVRV, NUPL, SOPR → нужен Realized Cap
- Puell Multiple → нужен daily miner revenue
- Reserve Risk → нужен HODL Bank (CDD-based)
- HODL Waves → нужно UTXO age distribution
- Exchange metrics → нужны labeled exchange addresses
- Hash Ribbons → нужен hashrate (доступен через blockchain.com)

### Rate Limiting Strategy:
- BGeometrics: 8 req/hr → кэшировать агрессивно, обновлять 1-2x/день
- CoinMetrics: 10 req/6sec → batch multiple metrics в один запрос
- Blockchain.com: без явных лимитов → но не злоупотреблять
- CoinGecko: 100 req/min → достаточно для real-time

### Storage:
- DuckDB для historical data (уже в проекте)
- Daily refresh для on-chain metrics (они меняются 1x/день)
- Ценовые данные: 5-15 min refresh для real-time dashboard
"""

if __name__ == "__main__":
    print("=== Bitcoin Macro Cycle Indicators Reference ===\n")
    for key, ind in INDICATORS.items():
        status = ind.get("status", "ACTIVE")
        print(f"  [{status}] {ind['name']}")
    print(f"\n  Total indicators: {len(INDICATORS)}")
    print(f"\n  Free data sources: {len(FREE_DATA_SOURCES)}")
    print("\n  Run: python research/btc_cycle_indicators.py")
