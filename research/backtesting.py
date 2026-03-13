"""Backtesting module for astro-score based BTC strategies.

Simulates buy/sell signals based on astro_score thresholds
and calculates PnL, Sharpe ratio, max drawdown, and equity curve.

Can be run standalone:
    python research/backtesting.py

Or used via API endpoint /api/backtest.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import duckdb

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "btc_research.duckdb")


@dataclass
class BacktestConfig:
    """Strategy configuration."""
    buy_score_threshold: float = 1.0     # Buy when astro score >= threshold
    sell_score_threshold: float = -0.5   # Sell when astro score <= threshold
    hold_days: int = 0                   # Minimum hold period after buy (0 = no minimum)
    initial_capital: float = 10000.0     # Starting capital in USD
    position_size: float = 1.0           # Fraction of capital to deploy (0.0-1.0)
    use_direction: bool = True           # Also consider direction signal
    sample_split: Literal["test", "train", "all"] = "test"  # holdout / in-sample / both


@dataclass
class TradeRecord:
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    pnl_pct: float
    pnl_usd: float
    hold_days: int
    entry_score: float
    exit_score: float


@dataclass
class BacktestResult:
    config: dict
    # Summary
    total_return_pct: float = 0.0
    buy_hold_return_pct: float = 0.0
    sharpe_ratio: float | None = None
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    avg_trade_pnl_pct: float = 0.0
    avg_hold_days: float = 0.0
    exposure_pct: float = 0.0   # % of time in market
    # Detailed
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)
    monthly_returns: list[dict] = field(default_factory=list)
    period_start: str = ""
    period_end: str = ""
    total_days: int = 0


_VALID_SPLITS = {"test", "train", "all"}


def _load_data(config: BacktestConfig) -> list[dict]:
    """Load aligned daily + astro data from DuckDB."""
    if config.sample_split not in _VALID_SPLITS:
        raise ValueError(f"Invalid sample_split: {config.sample_split!r}")

    conn = duckdb.connect(DB_PATH, read_only=True)
    try:
        params: list = []
        split_clause = ""
        if config.sample_split != "all":
            split_clause = "AND h.sample_split = ?"
            params.append(config.sample_split)

        rows = conn.execute(f"""
            SELECT
                d.date,
                d.close,
                h.score AS astro_score,
                h.direction AS astro_direction
            FROM btc_daily d
            JOIN btc_astro_history h ON h.date = d.date
            WHERE d.close IS NOT NULL
              AND h.score IS NOT NULL
              {split_clause}
            ORDER BY d.date
        """, params).fetchall()

        cols = ["date", "close", "astro_score", "astro_direction"]
        return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()


def run_backtest(config: BacktestConfig | None = None) -> BacktestResult:
    """Run a backtest with the given configuration."""
    if config is None:
        config = BacktestConfig()

    data = _load_data(config)
    if len(data) < 2:
        return BacktestResult(config=_config_to_dict(config))

    capital = config.initial_capital
    position = 0.0          # BTC held
    entry_price = 0.0
    entry_date = ""
    entry_score = 0.0
    days_held = 0
    in_position = False

    trades: list[TradeRecord] = []
    equity_curve: list[dict] = []
    daily_returns: list[float] = []
    days_in_market = 0
    prev_equity = capital

    for i, row in enumerate(data):
        date = row["date"]
        close = float(row["close"])
        score = float(row["astro_score"])
        direction = int(row["astro_direction"]) if row["astro_direction"] is not None else 0

        if in_position:
            days_held += 1
            days_in_market += 1

        # Current equity
        if in_position:
            current_equity = capital + position * close
        else:
            current_equity = capital

        daily_ret = (current_equity / prev_equity - 1.0) if prev_equity > 0 else 0.0
        daily_returns.append(daily_ret)
        prev_equity = current_equity

        equity_curve.append({
            "date": date,
            "equity": round(current_equity, 2),
            "close": close,
            "score": score,
            "in_position": in_position,
        })

        # --- Signal logic ---
        buy_signal = score >= config.buy_score_threshold
        if config.use_direction and direction < 0:
            buy_signal = False

        sell_signal = score <= config.sell_score_threshold
        if config.use_direction and direction > 0:
            sell_signal = False

        can_sell = days_held >= config.hold_days if config.hold_days > 0 else True

        # Execute trades
        if not in_position and buy_signal:
            deploy = capital * config.position_size
            position = deploy / close
            capital -= deploy
            entry_price = close
            entry_date = date
            entry_score = score
            days_held = 0
            in_position = True

        elif in_position and sell_signal and can_sell:
            proceeds = position * close
            pnl_usd = proceeds - (position * entry_price)
            pnl_pct = close / entry_price - 1.0
            capital += proceeds
            trades.append(TradeRecord(
                entry_date=entry_date,
                entry_price=round(entry_price, 2),
                exit_date=date,
                exit_price=round(close, 2),
                pnl_pct=round(pnl_pct * 100, 2),
                pnl_usd=round(pnl_usd, 2),
                hold_days=days_held,
                entry_score=round(entry_score, 2),
                exit_score=round(score, 2),
            ))
            position = 0.0
            in_position = False

    # Close open position at end
    if in_position and data:
        last_close = float(data[-1]["close"])
        proceeds = position * last_close
        pnl_usd = proceeds - (position * entry_price)
        pnl_pct = last_close / entry_price - 1.0
        capital += proceeds
        trades.append(TradeRecord(
            entry_date=entry_date,
            entry_price=round(entry_price, 2),
            exit_date=data[-1]["date"],
            exit_price=round(last_close, 2),
            pnl_pct=round(pnl_pct * 100, 2),
            pnl_usd=round(pnl_usd, 2),
            hold_days=days_held,
            entry_score=round(entry_score, 2),
            exit_score=round(float(data[-1]["astro_score"]), 2),
        ))
        position = 0.0

    # --- Calculate metrics ---
    final_equity = capital
    total_return_pct = (final_equity / config.initial_capital - 1.0) * 100
    buy_hold_return = (float(data[-1]["close"]) / float(data[0]["close"]) - 1.0) * 100

    # Sharpe ratio (annualized, assuming 365 trading days for crypto)
    sharpe = None
    if len(daily_returns) > 1:
        avg_ret = sum(daily_returns) / len(daily_returns)
        std_ret = math.sqrt(sum((r - avg_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1))
        if std_ret > 0:
            sharpe = round((avg_ret / std_ret) * math.sqrt(365), 2)

    # Max drawdown
    peak = 0.0
    max_dd = 0.0
    for point in equity_curve:
        eq = point["equity"]
        peak = max(peak, eq)
        dd = (eq - peak) / peak if peak > 0 else 0
        max_dd = min(max_dd, dd)

    # Win rate
    winning = sum(1 for t in trades if t.pnl_pct > 0)
    win_rate = (winning / len(trades) * 100) if trades else 0

    # Average trade metrics
    avg_pnl = sum(t.pnl_pct for t in trades) / len(trades) if trades else 0
    avg_hold = sum(t.hold_days for t in trades) / len(trades) if trades else 0

    # Monthly returns
    monthly: dict[str, list[float]] = {}
    for point in equity_curve:
        month_key = point["date"][:7]  # YYYY-MM
        if month_key not in monthly:
            monthly[month_key] = []
    # Simple: first and last equity per month
    month_equities: dict[str, tuple[float, float]] = {}
    for point in equity_curve:
        mk = point["date"][:7]
        if mk not in month_equities:
            month_equities[mk] = (point["equity"], point["equity"])
        else:
            month_equities[mk] = (month_equities[mk][0], point["equity"])

    monthly_returns = [
        {"month": mk, "return_pct": round((last / first - 1.0) * 100, 2)}
        for mk, (first, last) in sorted(month_equities.items())
        if first > 0
    ]

    exposure = (days_in_market / len(data) * 100) if data else 0

    return BacktestResult(
        config=_config_to_dict(config),
        total_return_pct=round(total_return_pct, 2),
        buy_hold_return_pct=round(buy_hold_return, 2),
        sharpe_ratio=sharpe,
        max_drawdown_pct=round(max_dd * 100, 2),
        win_rate=round(win_rate, 1),
        total_trades=len(trades),
        avg_trade_pnl_pct=round(avg_pnl, 2),
        avg_hold_days=round(avg_hold, 1),
        exposure_pct=round(exposure, 1),
        trades=[_trade_to_dict(t) for t in trades],
        equity_curve=equity_curve[::max(1, len(equity_curve) // 500)],  # downsample for API
        monthly_returns=monthly_returns,
        period_start=data[0]["date"] if data else "",
        period_end=data[-1]["date"] if data else "",
        total_days=len(data),
    )


def _config_to_dict(c: BacktestConfig) -> dict:
    return {
        "buy_score_threshold": c.buy_score_threshold,
        "sell_score_threshold": c.sell_score_threshold,
        "hold_days": c.hold_days,
        "initial_capital": c.initial_capital,
        "position_size": c.position_size,
        "use_direction": c.use_direction,
        "sample_split": c.sample_split,
    }


def _trade_to_dict(t: TradeRecord) -> dict:
    return {
        "entry_date": t.entry_date,
        "entry_price": t.entry_price,
        "exit_date": t.exit_date,
        "exit_price": t.exit_price,
        "pnl_pct": t.pnl_pct,
        "pnl_usd": t.pnl_usd,
        "hold_days": t.hold_days,
        "entry_score": t.entry_score,
        "exit_score": t.exit_score,
    }


if __name__ == "__main__":
    import json

    # Default backtest
    result = run_backtest()
    print(f"\n{'='*60}")
    print(f"  BACKTEST RESULTS ({result.period_start} → {result.period_end})")
    print(f"{'='*60}")
    print(f"  Strategy return:  {result.total_return_pct:+.2f}%")
    print(f"  Buy & Hold:       {result.buy_hold_return_pct:+.2f}%")
    print(f"  Sharpe ratio:     {result.sharpe_ratio}")
    print(f"  Max drawdown:     {result.max_drawdown_pct:.2f}%")
    print(f"  Win rate:         {result.win_rate:.1f}%")
    print(f"  Total trades:     {result.total_trades}")
    print(f"  Avg PnL/trade:    {result.avg_trade_pnl_pct:+.2f}%")
    print(f"  Avg hold:         {result.avg_hold_days:.1f} days")
    print(f"  Exposure:         {result.exposure_pct:.1f}%")
    print(f"  Period:           {result.total_days} days")
    print(f"{'='*60}")

    # Sweep thresholds
    print("\n  Threshold sweep:")
    print(f"  {'Buy ≥':<8} {'Sell ≤':<8} {'Return':<10} {'B&H':<10} {'Sharpe':<8} {'MaxDD':<8} {'Trades':<8} {'WinR':<8}")
    for buy_t in [0.5, 1.0, 1.5, 2.0]:
        for sell_t in [-1.0, -0.5, 0.0]:
            cfg = BacktestConfig(buy_score_threshold=buy_t, sell_score_threshold=sell_t)
            r = run_backtest(cfg)
            print(
                f"  {buy_t:<8.1f} {sell_t:<8.1f} {r.total_return_pct:<10.2f} "
                f"{r.buy_hold_return_pct:<10.2f} {str(r.sharpe_ratio):<8} "
                f"{r.max_drawdown_pct:<8.2f} {r.total_trades:<8} {r.win_rate:<8.1f}"
            )
