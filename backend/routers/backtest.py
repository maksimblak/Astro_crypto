"""Backtest endpoint: /api/backtest."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from backend.services import cache_service

router = APIRouter(tags=["backtest"])

BACKTEST_CACHE_TTL = 1800  # 30 minutes


@router.get("/backtest")
def api_backtest(
    buy_threshold: float = Query(1.0, description="Buy when astro score >= this"),
    sell_threshold: float = Query(-0.5, description="Sell when astro score <= this"),
    hold_days: int = Query(0, ge=0, description="Minimum hold days after buy"),
    position_size: float = Query(1.0, ge=0.1, le=1.0, description="Fraction of capital to deploy"),
    use_direction: bool = Query(True, description="Also consider direction signal"),
    sample_split: Literal["test", "train", "all"] = Query("test", description="test/train/all"),
):
    cache_key = f"backtest:{buy_threshold}:{sell_threshold}:{hold_days}:{position_size}:{use_direction}:{sample_split}"
    cached = cache_service.get(cache_key)
    if cached is not None:
        return cached

    from research.backtesting import BacktestConfig, run_backtest

    config = BacktestConfig(
        buy_score_threshold=buy_threshold,
        sell_score_threshold=sell_threshold,
        hold_days=hold_days,
        position_size=position_size,
        use_direction=use_direction,
        sample_split=sample_split,
    )
    result = run_backtest(config)

    # Convert dataclass to dict
    payload = {
        "config": result.config,
        "total_return_pct": result.total_return_pct,
        "buy_hold_return_pct": result.buy_hold_return_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "max_drawdown_pct": result.max_drawdown_pct,
        "win_rate": result.win_rate,
        "total_trades": result.total_trades,
        "avg_trade_pnl_pct": result.avg_trade_pnl_pct,
        "avg_hold_days": result.avg_hold_days,
        "exposure_pct": result.exposure_pct,
        "trades": result.trades,
        "equity_curve": result.equity_curve,
        "monthly_returns": result.monthly_returns,
        "period_start": result.period_start,
        "period_end": result.period_end,
        "total_days": result.total_days,
    }

    cache_service.set(cache_key, payload, ttl=BACKTEST_CACHE_TTL)
    return payload
