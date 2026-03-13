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

# Confirmed cycle tops (past cycles, verified)
CYCLE_TOPS_CONFIRMED = [
    date(2011, 6, 8),
    date(2013, 12, 4),
    date(2017, 12, 17),
    date(2021, 11, 10),
]
CYCLE_TOP_PRICES_CONFIRMED = [31.91, 1177.0, 19783.0, 69000.0]

# Current ATH — NOT a confirmed cycle top (cycle may still be ongoing)
CURRENT_ATH_DATE = date(2025, 1, 20)
CURRENT_ATH_PRICE = 109114.0

# All tops including current ATH (for display purposes)
CYCLE_TOPS = [*CYCLE_TOPS_CONFIRMED, CURRENT_ATH_DATE]
CYCLE_TOP_PRICES = [*CYCLE_TOP_PRICES_CONFIRMED, CURRENT_ATH_PRICE]

CYCLE_BOTTOMS = [
    date(2011, 11, 18),
    date(2015, 1, 14),
    date(2018, 12, 15),
    date(2022, 11, 21),
]

CYCLE_BOTTOM_PRICES = [2.01, 152.0, 3122.0, 15460.0]

assert len(CYCLE_TOPS_CONFIRMED) == len(CYCLE_TOP_PRICES_CONFIRMED)
assert len(CYCLE_BOTTOMS) == len(CYCLE_BOTTOM_PRICES)

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
    """Calculate average days from halving to cycle peak using CONFIRMED tops only."""
    # Pair halvings with subsequent confirmed tops (exclude current unconfirmed ATH)
    pairs = []
    for halving in HALVINGS:
        for top in CYCLE_TOPS_CONFIRMED:
            if top > halving:
                pairs.append({
                    "halving": halving.isoformat(),
                    "peak": top.isoformat(),
                    "days": (top - halving).days,
                    "confirmed": True,
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

    # Top-to-top model as cross-check (using confirmed tops only)
    top_to_top_days = []
    for i in range(1, len(CYCLE_TOPS_CONFIRMED)):
        top_to_top_days.append((CYCLE_TOPS_CONFIRMED[i] - CYCLE_TOPS_CONFIRMED[i - 1]).days)
    avg_top_to_top = int(np.mean(top_to_top_days)) if top_to_top_days else 1430
    top_to_top_projection = CYCLE_TOPS_CONFIRMED[-1] + timedelta(days=avg_top_to_top)

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
    # Calculate ROI per CONFIRMED cycle only (bottom to confirmed top)
    confirmed_rois = []
    for i, (bottom_price, top_price) in enumerate(
        zip(CYCLE_BOTTOM_PRICES, CYCLE_TOP_PRICES_CONFIRMED[1:])
    ):
        roi = top_price / bottom_price
        confirmed_rois.append({
            "cycle": i + 2,
            "bottom": bottom_price,
            "top": top_price,
            "roi_x": round(roi, 1),
            "confirmed": True,
        })

    # Decay factors between confirmed cycles
    decay_factors = []
    for i in range(1, len(confirmed_rois)):
        decay = confirmed_rois[i - 1]["roi_x"] / confirmed_rois[i]["roi_x"]
        decay_factors.append(round(decay, 2))

    avg_decay = float(np.mean(decay_factors)) if decay_factors else 4.5

    # Current cycle (ongoing, unconfirmed)
    current_bottom = CYCLE_BOTTOM_PRICES[-1]  # $15460
    current_ath = CURRENT_ATH_PRICE  # $109114 (ATH, not confirmed top)
    current_roi_actual = current_ath / current_bottom

    # What the decay model projected for current cycle
    last_confirmed_roi = confirmed_rois[-1]["roi_x"] if confirmed_rois else 22.1
    projected_current_roi = last_confirmed_roi / avg_decay
    projected_current_peak = current_bottom * projected_current_roi
    # Actual already exceeded? Track outperformance
    current_outperformance = current_roi_actual / projected_current_roi if projected_current_roi > 0 else 1.0

    # Add current cycle as unconfirmed row
    all_rois = [*confirmed_rois, {
        "cycle": len(confirmed_rois) + 2,
        "bottom": current_bottom,
        "top": current_ath,
        "roi_x": round(current_roi_actual, 1),
        "confirmed": False,
    }]

    # Bear drawdowns diminishing: 93% → 87% → 84% → 77%
    drawdowns = [0.93, 0.87, 0.84, 0.77]
    avg_drawdown_decay = float(np.mean(
        [drawdowns[i] / drawdowns[i + 1] for i in range(len(drawdowns) - 1)]
    ))
    projected_drawdown = drawdowns[-1] / avg_drawdown_decay
    projected_drawdown = min(projected_drawdown, 0.75)  # cap at 75%

    # Project next cycle (after 2028 halving) from current ATH
    projected_next_bottom = current_ath * (1 - projected_drawdown)
    # Use actual current cycle ROI for next cycle decay (since we already know it)
    next_cycle_roi = current_roi_actual / avg_decay
    next_cycle_roi_conservative = current_roi_actual / (avg_decay * 1.5)
    projected_next_peak = projected_next_bottom * next_cycle_roi
    projected_next_peak_conservative = projected_next_bottom * next_cycle_roi_conservative

    return {
        "cycle_rois": all_rois,
        "decay_factors": decay_factors,
        "avg_decay": round(avg_decay, 2),
        # Current cycle stats
        "current_cycle_bottom": current_bottom,
        "current_cycle_top": current_ath,
        "current_cycle_roi_x": round(current_roi_actual, 1),
        "current_cycle_projected_roi_x": round(projected_current_roi, 1),
        "current_cycle_projected_peak": round(projected_current_peak, 0),
        "current_outperformance": round(current_outperformance, 2),
        # Next cycle projections (post-2028 halving)
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

    # Moving averages (with NaN guard)
    sma200_raw = close.rolling(200, min_periods=200).mean().iloc[-1]
    sma350_raw = close.rolling(350, min_periods=350).mean().iloc[-1]
    sma111_raw = close.rolling(111, min_periods=111).mean().iloc[-1]

    if any(np.isnan(v) for v in [sma200_raw, sma350_raw, sma111_raw]):
        raise ValueError(
            f"Insufficient data for SMA: sma200={sma200_raw}, sma350={sma350_raw}, "
            f"sma111={sma111_raw}. Need at least 350 rows of non-NaN close prices."
        )

    sma200 = float(sma200_raw)
    sma350 = float(sma350_raw)
    sma111 = float(sma111_raw)
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

    # Project power law for peak date and next halving peak
    peak_date_str = timing["projected_peak"]
    peak_date = datetime.strptime(peak_date_str, "%Y-%m-%d").date()
    pl_fair_at_peak = power_law_price(pl_params, peak_date)
    pl_band_at_peak = power_law_band(pl_params, peak_date, 2.0)

    # ── Current cycle targets (THIS cycle, halving 2024) ──
    current_cycle_targets = [
        gr_ceiling["projected_ceiling"],          # Golden ratio ×2 ceiling
        pl_band_at_peak[1],                       # Power law +2σ at projected peak
        pl_fair_at_peak,                          # Power law fair at projected peak
    ]
    current_cycle_targets = sorted([p for p in current_cycle_targets if p and p > 0])
    current_median = float(np.median(current_cycle_targets)) if current_cycle_targets else None

    # ── Next cycle targets (post-2028 halving) ──
    next_halving_est_str = timing["next_halving_est"]
    next_halving_date = datetime.strptime(next_halving_est_str, "%Y-%m-%d").date()
    next_peak_est = next_halving_date + timedelta(days=timing["halving_model"]["avg_days"])
    pl_fair_next = power_law_price(pl_params, next_peak_est)
    pl_band_next = power_law_band(pl_params, next_peak_est, 2.0)

    next_cycle_targets = [
        dim_returns["projected_peak_conservative"],
        dim_returns["projected_peak_from_bottom"],
        gr_ceiling["next_cycle_ceiling"],
        pl_fair_next,                              # Power law fair (not +2σ — too speculative)
    ]
    next_cycle_targets = sorted([p for p in next_cycle_targets if p and p > 0])
    next_median = float(np.median(next_cycle_targets)) if next_cycle_targets else None

    # Peak status assessment
    days_to_peak = timing["days_to_projected_peak"]
    peak_window_late_str = timing["peak_window_late"]
    peak_window_late = datetime.strptime(peak_window_late_str, "%Y-%m-%d").date()
    peak_passed = reference_date > peak_window_late

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
            "days_to_peak": days_to_peak,
            "peak_window": [timing["peak_window_early"], timing["peak_window_late"]],
            "peak_passed": peak_passed,
            "top_to_top_check": timing["top_to_top_projection"],
            # Current cycle (halving 2024)
            "current_cycle_targets": [round(p, 0) for p in current_cycle_targets],
            "current_cycle_median": round(current_median, 0) if current_median else None,
            # Next cycle (halving ~2028)
            "next_cycle_targets": [round(p, 0) for p in next_cycle_targets],
            "next_cycle_median": round(next_median, 0) if next_median else None,
            "next_cycle_peak_est": next_peak_est.isoformat(),
        },
    }
