"""Price-only projection models for BTC cycle top/bottom forecasting.

All models use only OHLCV data (yfinance) — no external API required.

Models:
1. Power Law — log-log regression, price corridor for any future date
2. Golden Ratio Multiplier — 350DMA × declining Fibonacci levels
3. Halving Timing — average days from halving to cycle peak
4. Diminishing Returns — decay factor for ROI per cycle
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import NamedTuple

import numpy as np
import pandas as pd


# ── BTC Halving dates ──────────────────────────────────────────────

BTC_GENESIS = date(2009, 1, 3)

HALVINGS = [
    date(2012, 11, 28),
    date(2016, 7, 9),
    date(2020, 5, 11),
    date(2024, 4, 20),
]

CYCLE_TOPS = [
    date(2011, 6, 8),
    date(2013, 12, 4),
    date(2017, 12, 17),
    date(2021, 11, 10),
    date(2025, 1, 20),
]

CYCLE_BOTTOMS = [
    date(2011, 11, 18),
    date(2015, 1, 14),
    date(2018, 12, 15),
    date(2022, 11, 21),
]

CYCLE_TOP_PRICES = [31.91, 1177.0, 19783.0, 69000.0, 109114.0]
CYCLE_BOTTOM_PRICES = [2.01, 152.0, 3122.0, 15460.0]

# Fibonacci levels used by Golden Ratio Multiplier (historically declining)
GOLDEN_FIB_LEVELS = [21, 13, 8, 5, 3, 2, 1.618]


# ── Power Law Model ────────────────────────────────────────────────

class PowerLawParams(NamedTuple):
    slope: float
    intercept: float
    r_squared: float
    residual_std: float


def fit_power_law(dates: pd.Series, prices: pd.Series) -> PowerLawParams:
    """Fit log10(price) = slope * log10(days_since_genesis) + intercept."""
    dt_index = pd.to_datetime(dates)
    days = np.array([(d.date() - BTC_GENESIS).days for d in dt_index], dtype=float)

    mask = (days > 0) & (prices > 0)
    log_days = np.log10(days[mask])
    log_price = np.log10(prices[mask].values.astype(float))

    slope, intercept = np.polyfit(log_days, log_price, 1)

    predicted = slope * log_days + intercept
    ss_res = np.sum((log_price - predicted) ** 2)
    ss_tot = np.sum((log_price - np.mean(log_price)) ** 2)
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    residual_std = float(np.std(log_price - predicted))

    return PowerLawParams(
        slope=float(slope),
        intercept=float(intercept),
        r_squared=float(r_squared),
        residual_std=float(residual_std),
    )


def power_law_price(params: PowerLawParams, target_date: date) -> float:
    """Fair value price for a given date."""
    days = (target_date - BTC_GENESIS).days
    if days <= 0:
        return 0.0
    log_price = params.slope * np.log10(days) + params.intercept
    return float(10 ** log_price)


def power_law_band(
    params: PowerLawParams,
    target_date: date,
    sigma: float = 1.0,
) -> tuple[float, float]:
    """Price band at ±sigma standard deviations from fair value."""
    days = (target_date - BTC_GENESIS).days
    if days <= 0:
        return (0.0, 0.0)
    log_fair = params.slope * np.log10(days) + params.intercept
    lower = float(10 ** (log_fair - sigma * params.residual_std))
    upper = float(10 ** (log_fair + sigma * params.residual_std))
    return (lower, upper)


def power_law_position(params: PowerLawParams, target_date: date, price: float) -> float:
    """Where current price sits in the power law band. 0 = -2σ, 0.5 = fair, 1.0 = +2σ."""
    days = (target_date - BTC_GENESIS).days
    if days <= 0 or price <= 0:
        return 0.5
    log_price = np.log10(price)
    log_fair = params.slope * np.log10(days) + params.intercept
    deviation = (log_price - log_fair) / params.residual_std if params.residual_std > 0 else 0.0
    return float(np.clip((deviation + 2.0) / 4.0, 0.0, 1.0))


# ── Golden Ratio Multiplier ───────────────────────────────────────

def golden_ratio_levels(sma350: float) -> list[dict]:
    """Calculate price levels at each Fibonacci multiple of 350DMA."""
    levels = []
    for fib in GOLDEN_FIB_LEVELS:
        levels.append({
            "fib": fib,
            "price": round(sma350 * fib, 2),
        })
    return levels


def golden_ratio_current_ceiling(sma350: float, cycle_index: int = 5) -> dict:
    """The expected ceiling for the current/next cycle based on diminishing Fib levels.

    cycle_index: 0=2011(×21), 1=2013(×13), 2=2014(×8), 3=2017(×5), 4=2021(×3), 5=2025(×2), 6=next(×1.618)
    """
    idx = min(cycle_index, len(GOLDEN_FIB_LEVELS) - 1)
    fib = GOLDEN_FIB_LEVELS[idx]
    return {
        "fib_level": fib,
        "projected_ceiling": round(sma350 * fib, 2),
        "next_cycle_fib": GOLDEN_FIB_LEVELS[min(idx + 1, len(GOLDEN_FIB_LEVELS) - 1)],
        "next_cycle_ceiling": round(sma350 * GOLDEN_FIB_LEVELS[min(idx + 1, len(GOLDEN_FIB_LEVELS) - 1)], 2),
    }


# ── Halving Timing Model ──────────────────────────────────────────

def halving_to_peak_stats() -> dict:
    """Calculate average days from halving to cycle peak."""
    # Pair halvings with subsequent tops
    pairs = []
    for halving in HALVINGS:
        # Find the first top after this halving
        for top in CYCLE_TOPS:
            if top > halving:
                pairs.append({
                    "halving": halving.isoformat(),
                    "peak": top.isoformat(),
                    "days": (top - halving).days,
                })
                break

    days_list = [p["days"] for p in pairs]
    # Use last 3 cycles (more stable)
    recent_days = days_list[-3:] if len(days_list) >= 3 else days_list

    avg_days = int(np.mean(recent_days)) if recent_days else 537
    std_days = int(np.std(recent_days)) if len(recent_days) > 1 else 25

    return {
        "history": pairs,
        "avg_days": avg_days,
        "std_days": std_days,
        "recent_cycles_used": len(recent_days),
    }


def project_next_peak(reference_date: date | None = None) -> dict:
    """Project the next cycle peak date based on halving timing model."""
    if reference_date is None:
        reference_date = date.today()

    stats = halving_to_peak_stats()
    avg_days = stats["avg_days"]
    std_days = stats["std_days"]

    # Find current or next halving
    last_halving = HALVINGS[-1]
    projected_peak = last_halving + timedelta(days=avg_days)
    peak_early = last_halving + timedelta(days=avg_days - std_days * 2)
    peak_late = last_halving + timedelta(days=avg_days + std_days * 2)

    days_to_peak = (projected_peak - reference_date).days

    # Top-to-top model as cross-check
    top_to_top_days = []
    for i in range(1, len(CYCLE_TOPS)):
        top_to_top_days.append((CYCLE_TOPS[i] - CYCLE_TOPS[i - 1]).days)
    avg_top_to_top = int(np.mean(top_to_top_days)) if top_to_top_days else 1430
    top_to_top_projection = CYCLE_TOPS[-1] + timedelta(days=avg_top_to_top)

    # Next halving estimate (~4 years = 1460 days after last one, actually ~210000 blocks)
    next_halving_est = last_halving + timedelta(days=1461)

    return {
        "last_halving": last_halving.isoformat(),
        "projected_peak": projected_peak.isoformat(),
        "peak_window_early": peak_early.isoformat(),
        "peak_window_late": peak_late.isoformat(),
        "days_to_projected_peak": days_to_peak,
        "halving_model": stats,
        "top_to_top_avg_days": avg_top_to_top,
        "top_to_top_projection": top_to_top_projection.isoformat(),
        "next_halving_est": next_halving_est.isoformat(),
    }


# ── Diminishing Returns Model ─────────────────────────────────────

def diminishing_returns_projection() -> dict:
    """Project current and next cycle based on diminishing returns pattern."""
    # Calculate ROI per completed cycle (bottom to top)
    cycle_rois = []
    for i, (bottom_price, top_price) in enumerate(
        zip(CYCLE_BOTTOM_PRICES, CYCLE_TOP_PRICES[1:])
    ):
        roi = top_price / bottom_price
        cycle_rois.append({
            "cycle": i + 2,
            "bottom": bottom_price,
            "top": top_price,
            "roi_x": round(roi, 1),
        })

    # Decay factors between cycles
    decay_factors = []
    for i in range(1, len(cycle_rois)):
        decay = cycle_rois[i - 1]["roi_x"] / cycle_rois[i]["roi_x"]
        decay_factors.append(round(decay, 2))

    avg_decay = float(np.mean(decay_factors)) if decay_factors else 3.0

    # Current cycle: bottom $15460 (Nov 2022), current top $109114 (Jan 2025)
    # This is the ONGOING cycle — project its remaining upside
    current_bottom = CYCLE_BOTTOM_PRICES[-1]  # $15460
    current_top = CYCLE_TOP_PRICES[-1]  # $109114 (current ATH)
    current_roi = current_top / current_bottom  # ~7.1×

    # Bear drawdowns diminishing: 93% → 87% → 84% → 77%
    drawdowns = [0.93, 0.87, 0.84, 0.77]
    avg_drawdown_decay = float(np.mean(
        [drawdowns[i] / drawdowns[i + 1] for i in range(len(drawdowns) - 1)]
    ))
    projected_drawdown = drawdowns[-1] / avg_drawdown_decay
    projected_drawdown = min(projected_drawdown, 0.75)  # cap at 75%

    # Project next cycle (after 2028 halving)
    projected_next_bottom = current_top * (1 - projected_drawdown)
    last_roi = cycle_rois[-1]["roi_x"] if cycle_rois else 4.0
    next_cycle_roi = last_roi / avg_decay
    next_cycle_roi_conservative = last_roi / (avg_decay * 1.3)
    projected_next_peak = projected_next_bottom * next_cycle_roi
    projected_next_peak_conservative = projected_next_bottom * next_cycle_roi_conservative

    return {
        "cycle_rois": cycle_rois,
        "decay_factors": decay_factors,
        "avg_decay": round(avg_decay, 2),
        # Current cycle stats
        "current_cycle_bottom": current_bottom,
        "current_cycle_top": current_top,
        "current_cycle_roi_x": round(current_roi, 1),
        # Next cycle projections
        "projected_next_roi_x": round(next_cycle_roi, 1),
        "projected_next_roi_conservative_x": round(next_cycle_roi_conservative, 1),
        "projected_peak_from_bottom": round(projected_next_peak, 0),
        "projected_peak_conservative": round(projected_next_peak_conservative, 0),
        "bear_drawdowns": drawdowns,
        "projected_next_drawdown_pct": round(projected_drawdown * 100, 1),
        "projected_next_bottom": round(projected_next_bottom, 0),
    }


# ── Mayer Multiple ─────────────────────────────────────────────────

def mayer_multiple(price: float, sma200: float) -> float | None:
    """Price / 200DMA. Historically tops > 2.4, bottoms < 0.5."""
    if sma200 is None or sma200 <= 0:
        return None
    return round(price / sma200, 3)


# ── Pi Cycle Distance ──────────────────────────────────────────────

def pi_cycle_distance(sma111: float, sma350x2: float) -> float | None:
    """How far 111DMA is from crossing 350DMA×2. 0 = cross, negative = below."""
    if sma350x2 is None or sma350x2 <= 0:
        return None
    return round(sma111 / sma350x2 - 1.0, 4)


# ── Composite Projection ──────────────────────────────────────────

def build_projections(
    df_ohlcv: pd.DataFrame,
    reference_date: date | None = None,
) -> dict:
    """Build all projection models from OHLCV data.

    Returns a dict ready to be serialized to JSON in the /api/cycle endpoint.
    """
    if reference_date is None:
        reference_date = date.today()

    close = pd.to_numeric(df_ohlcv["Close"] if "Close" in df_ohlcv.columns else df_ohlcv["close"], errors="coerce")
    dates = pd.to_datetime(df_ohlcv.index)

    current_price = float(close.iloc[-1])

    # Moving averages
    sma200 = float(close.rolling(200, min_periods=200).mean().iloc[-1])
    sma350 = float(close.rolling(350, min_periods=350).mean().iloc[-1])
    sma111 = float(close.rolling(111, min_periods=111).mean().iloc[-1])
    sma350x2 = sma350 * 2.0

    # 1. Power Law
    pl_params = fit_power_law(dates.strftime("%Y-%m-%d"), close)
    pl_fair = power_law_price(pl_params, reference_date)
    pl_band_1s = power_law_band(pl_params, reference_date, 1.0)
    pl_band_2s = power_law_band(pl_params, reference_date, 2.0)
    pl_position = power_law_position(pl_params, reference_date, current_price)

    # 2. Golden Ratio
    gr_levels = golden_ratio_levels(sma350)
    gr_ceiling = golden_ratio_current_ceiling(sma350, cycle_index=5)

    # 3. Halving Timing
    timing = project_next_peak(reference_date)

    # 4. Diminishing Returns
    dim_returns = diminishing_returns_projection()

    # 5. Mayer Multiple
    mm = mayer_multiple(current_price, sma200)

    # 6. Pi Cycle Distance
    pi_dist = pi_cycle_distance(sma111, sma350x2)

    # Project power law for next peak date
    peak_date_str = timing["projected_peak"]
    peak_date = datetime.strptime(peak_date_str, "%Y-%m-%d").date()
    pl_fair_at_peak = power_law_price(pl_params, peak_date)
    pl_band_at_peak = power_law_band(pl_params, peak_date, 2.0)

    # Composite projection summary
    # For the NEXT cycle (post-2028 halving): use dim returns + golden ratio next + power law at peak
    price_targets = [
        dim_returns["projected_peak_conservative"],
        dim_returns["projected_peak_from_bottom"],
        gr_ceiling["next_cycle_ceiling"],
        pl_band_at_peak[1],
    ]
    price_targets = [p for p in price_targets if p and p > 0]
    median_target = float(np.median(price_targets)) if price_targets else None

    return {
        "reference_date": reference_date.isoformat(),
        "current_price": round(current_price, 2),
        "power_law": {
            "fair_value": round(pl_fair, 2),
            "band_1sigma": [round(pl_band_1s[0], 2), round(pl_band_1s[1], 2)],
            "band_2sigma": [round(pl_band_2s[0], 2), round(pl_band_2s[1], 2)],
            "position": round(pl_position, 3),
            "r_squared": round(pl_params.r_squared, 4),
            "slope": round(pl_params.slope, 4),
            "intercept": round(pl_params.intercept, 4),
            "fair_at_projected_peak": round(pl_fair_at_peak, 2),
            "band_at_projected_peak": [round(pl_band_at_peak[0], 2), round(pl_band_at_peak[1], 2)],
        },
        "golden_ratio": {
            "sma350": round(sma350, 2),
            "levels": gr_levels,
            "current_ceiling": gr_ceiling,
        },
        "halving_timing": timing,
        "diminishing_returns": dim_returns,
        "mayer_multiple": mm,
        "pi_cycle_distance": pi_dist,
        "sma200": round(sma200, 2),
        "sma111": round(sma111, 2),
        "sma350x2": round(sma350x2, 2),
        "composite": {
            "projected_peak_date": timing["projected_peak"],
            "days_to_peak": timing["days_to_projected_peak"],
            "peak_window": [timing["peak_window_early"], timing["peak_window_late"]],
            "price_targets": [round(p, 0) for p in sorted(price_targets)],
            "median_target": round(median_target, 0) if median_target else None,
            "top_to_top_check": timing["top_to_top_projection"],
        },
    }
