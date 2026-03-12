"""Backtest market regime features on BTC daily history."""

from __future__ import annotations

import duckdb
from pathlib import Path

import pandas as pd

from astro_shared import DB_PATH


FEATURES = [
    ("amihud_z_90d", "Liquidity", "higher = more illiquid"),
    ("range_compression_20d", "Liquidity", "higher = expanded range"),
    ("wiki_views_z_30d", "Attention", "higher = more attention"),
    ("fear_greed_value", "Attention", "higher = greedier crowd"),
    ("funding_rate_z_30d", "Derivatives", "higher = more crowded longs"),
    ("perp_premium_daily", "Derivatives", "higher = richer perp premium"),
    ("perp_premium_z_30d", "Derivatives", "higher = richer perp premium vs baseline"),
    ("open_interest_z_30d", "Derivatives", "higher = more crowded OI"),
    ("unique_addresses_z_30d", "On-chain", "higher = more active network"),
    ("tx_count_z_30d", "On-chain", "higher = more transactions"),
    ("onchain_activity_z_30d", "On-chain", "higher = stronger on-chain composite"),
]
HORIZONS = [7, 20, 60]
TOP_QUANTILE = 0.80
BOTTOM_QUANTILE = 0.20
CONTEXT_SCORE_NAME = "context_score_v2"


def load_feature_frame() -> pd.DataFrame:
    conn = duckdb.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            """
            SELECT
                d.date,
                d.close,
                f.amihud_z_90d,
                f.range_compression_20d,
                f.wiki_views_z_30d,
                f.fear_greed_value,
                f.funding_rate_z_30d,
                f.perp_premium_daily,
                f.perp_premium_z_30d,
                f.open_interest_z_30d,
                f.unique_addresses_z_30d,
                f.tx_count_z_30d,
                f.onchain_activity_z_30d
            FROM btc_daily d
            LEFT JOIN btc_market_features f ON f.date = d.date
            ORDER BY d.date
            """,
            conn,
            parse_dates=["date"],
        )
    finally:
        conn.close()

    df = df.sort_values("date").reset_index(drop=True)
    for horizon in HORIZONS:
        df[f"future_return_{horizon}d"] = df["close"].shift(-horizon) / df["close"] - 1.0
    df[CONTEXT_SCORE_NAME] = build_context_score(df)
    return df


def build_context_score(df: pd.DataFrame) -> pd.Series:
    score = pd.Series(0, index=df.index, dtype=float)
    available_mask = df[
        [
            "fear_greed_value",
            "unique_addresses_z_30d",
            "wiki_views_z_30d",
            "perp_premium_daily",
            "open_interest_z_30d",
        ]
    ].notna().any(axis=1)

    fear = df["fear_greed_value"]
    score = score.where(~(fear >= 70), score + 3)
    score = score.where(~(fear <= 24), score - 3)

    addresses = df["unique_addresses_z_30d"]
    score = score.where(~(addresses >= 0.91), score + 2)
    score = score.where(~(addresses <= -0.90), score - 2)

    wiki = df["wiki_views_z_30d"]
    score = score.where(~(wiki >= 1.30), score + 2)
    score = score.where(~(wiki <= -1.20), score - 2)

    premium = df["perp_premium_daily"]
    score = score.where(~(premium >= 0.00019), score + 2)
    score = score.where(~(premium <= -0.00026), score - 2)

    oi = df["open_interest_z_30d"]
    score = score.where(~(oi <= -1.48), score + 1)
    score = score.where(~(oi >= 0.42), score - 1)

    score = score.where(available_mask, other=pd.NA)
    return score


def _rank_ic(feature: pd.Series, future_return: pd.Series) -> float | None:
    aligned = pd.DataFrame({"feature": feature, "future_return": future_return}).dropna()
    if len(aligned) < 20:
        return None
    return aligned["feature"].rank(pct=True).corr(aligned["future_return"].rank(pct=True))


def _coverage_meta(feature_series: pd.Series, dates: pd.Series) -> tuple[int, str | None, str | None]:
    valid = feature_series.notna()
    if not valid.any():
        return 0, None, None
    valid_dates = dates[valid]
    return int(valid.sum()), valid_dates.min().strftime("%Y-%m-%d"), valid_dates.max().strftime("%Y-%m-%d")


def backtest_feature(df: pd.DataFrame, feature_name: str, category: str, note: str) -> tuple[dict, list[dict]]:
    feature = df[feature_name]
    coverage_count, coverage_start, coverage_end = _coverage_meta(feature, df["date"])
    summary = {
        "feature": feature_name,
        "category": category,
        "note": note,
        "coverage_count": coverage_count,
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
    }
    details = []

    for horizon in HORIZONS:
        target = df[f"future_return_{horizon}d"]
        sample = pd.DataFrame(
            {
                "date": df["date"],
                "feature": feature,
                "future_return": target,
            }
        ).dropna()

        sample_count = len(sample)
        if sample_count < 50:
            summary.update(
                {
                    f"samples_{horizon}d": sample_count,
                    f"rank_ic_{horizon}d": None,
                    f"high_avg_{horizon}d": None,
                    f"low_avg_{horizon}d": None,
                    f"spread_{horizon}d": None,
                    f"best_side_{horizon}d": None,
                    f"edge_{horizon}d": None,
                    f"high_hit_up_{horizon}d": None,
                    f"low_hit_up_{horizon}d": None,
                }
            )
            continue

        high_cutoff = sample["feature"].quantile(TOP_QUANTILE)
        low_cutoff = sample["feature"].quantile(BOTTOM_QUANTILE)
        high_slice = sample[sample["feature"] >= high_cutoff]
        low_slice = sample[sample["feature"] <= low_cutoff]

        high_avg = high_slice["future_return"].mean()
        low_avg = low_slice["future_return"].mean()
        spread = high_avg - low_avg
        best_side = "high" if spread >= 0 else "low"
        edge = abs(spread)
        high_hit_up = (high_slice["future_return"] > 0).mean()
        low_hit_up = (low_slice["future_return"] > 0).mean()
        rank_ic = _rank_ic(sample["feature"], sample["future_return"])

        summary.update(
            {
                f"samples_{horizon}d": sample_count,
                f"rank_ic_{horizon}d": rank_ic,
                f"high_avg_{horizon}d": high_avg,
                f"low_avg_{horizon}d": low_avg,
                f"spread_{horizon}d": spread,
                f"best_side_{horizon}d": best_side,
                f"edge_{horizon}d": edge,
                f"high_hit_up_{horizon}d": high_hit_up,
                f"low_hit_up_{horizon}d": low_hit_up,
            }
        )
        details.append(
            {
                "feature": feature_name,
                "category": category,
                "horizon_days": horizon,
                "sample_count": sample_count,
                "coverage_start": coverage_start,
                "coverage_end": coverage_end,
                "rank_ic": rank_ic,
                "high_avg_return": high_avg,
                "low_avg_return": low_avg,
                "spread": spread,
                "best_side": best_side,
                "edge": edge,
                "high_hit_up": high_hit_up,
                "low_hit_up": low_hit_up,
            }
        )

    edge_values = [summary.get(f"edge_{horizon}d") for horizon in HORIZONS]
    weighted_values = [
        (summary.get("edge_7d") or 0.0) * 0.2,
        (summary.get("edge_20d") or 0.0) * 0.4,
        (summary.get("edge_60d") or 0.0) * 0.4,
    ]
    summary["composite_edge"] = sum(weighted_values)
    summary["best_horizon"] = max(
        HORIZONS,
        key=lambda horizon: summary.get(f"edge_{horizon}d") or -1,
    )
    summary["mean_edge"] = (
        sum(value for value in edge_values if value is not None) / len([value for value in edge_values if value is not None])
        if any(value is not None for value in edge_values)
        else None
    )
    return summary, details


def format_pct(value: float | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value * 100:.{digits}f}%"


def format_float(value: float | None, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.{digits}f}"


def main():
    df = load_feature_frame()

    summary_rows = []
    detail_rows = []
    for feature_name, category, note in FEATURES:
        summary, details = backtest_feature(df, feature_name, category, note)
        summary_rows.append(summary)
        detail_rows.extend(details)

    context_summary, context_details = backtest_feature(
        df,
        CONTEXT_SCORE_NAME,
        "Bundle",
        "weighted context score from fear & greed, active addresses, wikipedia attention, perp premium and open interest",
    )
    summary_rows.append(context_summary)
    detail_rows.extend(context_details)

    summary_df = pd.DataFrame(summary_rows).sort_values(
        ["composite_edge", "coverage_count"],
        ascending=[False, False],
    )
    detail_df = pd.DataFrame(detail_rows).sort_values(["horizon_days", "edge"], ascending=[True, False])

    data_dir = Path(DB_PATH).parent
    summary_path = data_dir / "market_feature_backtest_summary.csv"
    detail_path = data_dir / "market_feature_backtest_details.csv"
    summary_df.to_csv(summary_path, index=False)
    detail_df.to_csv(detail_path, index=False)

    print("Backtest summary saved:", summary_path)
    print("Backtest details saved:", detail_path)
    print()
    print("Top features by composite edge")
    print("=" * 100)
    for _, row in summary_df.head(11).iterrows():
        coverage = f"{row['coverage_start']} -> {row['coverage_end']} ({int(row['coverage_count'])} obs)"
        horizons = []
        for horizon in HORIZONS:
            edge = format_pct(row.get(f"edge_{horizon}d"))
            side = row.get(f"best_side_{horizon}d") or "—"
            rank_ic = format_float(row.get(f"rank_ic_{horizon}d"))
            horizons.append(f"{horizon}d edge {edge} [{side}] IC {rank_ic}")
        print(f"{row['feature']:<24} | {row['category']:<11} | {coverage}")
        print("  " + " | ".join(horizons))

    print()
    print("Context bundle")
    print("=" * 100)
    bundle = summary_df[summary_df["feature"] == CONTEXT_SCORE_NAME].iloc[0]
    bundle_coverage = f"{bundle['coverage_start']} -> {bundle['coverage_end']} ({int(bundle['coverage_count'])} obs)"
    print(f"{CONTEXT_SCORE_NAME:<24} | {bundle_coverage}")
    for horizon in HORIZONS:
        print(
            f"  {horizon}d edge {format_pct(bundle.get(f'edge_{horizon}d'))} "
            f"[{bundle.get(f'best_side_{horizon}d')}] "
            f"IC {format_float(bundle.get(f'rank_ic_{horizon}d'))}"
        )


if __name__ == "__main__":
    main()
