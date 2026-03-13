"""Market feature engineering for BTC daily data."""

from __future__ import annotations

import duckdb
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import yfinance as yf

try:
    from .config import DB_PATH, yfinance_exclusive_end
    from .derivatives_history import (
        aggregate_derivatives_history,
        fetch_derivatives_history,
        save_derivatives_history_to_db,
    )
except ImportError:
    from config import DB_PATH, yfinance_exclusive_end
    from derivatives_history import (
        aggregate_derivatives_history,
        fetch_derivatives_history,
        save_derivatives_history_to_db,
    )


FEATURE_SOURCE_VERSION = "market_features_v4"
HTTP_TIMEOUT = 30
HTTP_HEADERS = {
    "User-Agent": "AstroBTC/1.0 (market feature pipeline)",
}
PRESERVED_RAW_FEATURE_COLUMNS = [
    "wiki_views",
    "fear_greed_value",
    "unique_addresses",
    "tx_count",
    "dxy_close",
    "us10y_yield",
    "spx_close",
]
YFINANCE_TICKERS = {
    "dxy_close": ["DX-Y.NYB", "DX=F", "UUP"],
    "us10y_yield": "^TNX",
    "spx_close": "^GSPC",
}
MARKET_FEATURE_COLUMNS = {
    "date": "TEXT PRIMARY KEY",
    "dollar_volume": "REAL",
    "abs_return_1d": "REAL",
    "amihud_illiquidity": "REAL",
    "amihud_illiquidity_20d": "REAL",
    "amihud_z_90d": "REAL",
    "true_range_pct": "REAL",
    "range_compression_20d": "REAL",
    "wiki_views": "REAL",
    "wiki_views_7d": "REAL",
    "wiki_views_z_30d": "REAL",
    "fear_greed_value": "REAL",
    "fear_greed_z_30d": "REAL",
    "funding_rate_daily": "REAL",
    "funding_rate_z_30d": "REAL",
    "funding_source_count": "INTEGER",
    "perp_premium_daily": "REAL",
    "perp_premium_z_30d": "REAL",
    "perp_premium_source_count": "INTEGER",
    "open_interest_value": "REAL",
    "open_interest_delta_1d": "REAL",
    "open_interest_delta_z_30d": "REAL",
    "oi_price_state_1d": "TEXT",
    "open_interest_z_30d": "REAL",
    "open_interest_source_count": "INTEGER",
    "open_interest_primary_source": "TEXT",
    "funding_price_divergence_3d": "REAL",
    "funding_contrarian_bias_3d": "INTEGER",
    "unique_addresses": "REAL",
    "unique_addresses_z_30d": "REAL",
    "tx_count": "REAL",
    "tx_count_z_30d": "REAL",
    "onchain_activity_z_30d": "REAL",
    "dxy_close": "REAL",
    "dxy_return_20d": "REAL",
    "dxy_return_z_90d": "REAL",
    "us10y_yield": "REAL",
    "us10y_change_20d_bps": "REAL",
    "us10y_change_z_90d": "REAL",
    "spx_close": "REAL",
    "btc_spx_corr_30d": "REAL",
    "derivatives_source_version": "TEXT",
    "feature_source_version": "TEXT",
}


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {}
    for column in df.columns:
        lowered = str(column).lower()
        if lowered in {"open", "high", "low", "close", "volume"}:
            rename_map[column] = lowered
    normalized = df.rename(columns=rename_map).copy()
    required = ["open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in normalized.columns]
    if missing:
        raise ValueError(f"Missing OHLCV columns: {missing}")
    return normalized[required]


def _request_json(session: requests.Session, url: str, params: dict | None = None, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            response = session.get(url, params=params, timeout=HTTP_TIMEOUT, headers=HTTP_HEADERS)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
        except requests.HTTPError:
            raise


def _epoch_to_date(epoch_seconds: int | str) -> str:
    return datetime.fromtimestamp(int(epoch_seconds), tz=timezone.utc).strftime("%Y-%m-%d")


def _rolling_z(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    mean_series = series.rolling(window, min_periods=min_periods).mean()
    std_series = series.rolling(window, min_periods=min_periods).std(ddof=0)
    return (series - mean_series) / std_series.replace(0, np.nan)


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame({"date": pd.Series(dtype="object")})


def _load_existing_feature_snapshot(start_date: str, end_date: str) -> pd.DataFrame:
    select_columns = ", ".join(PRESERVED_RAW_FEATURE_COLUMNS)
    query = (
        f"SELECT date, {select_columns} "
        "FROM btc_market_features WHERE date >= ? AND date <= ? ORDER BY date"
    )
    conn = duckdb.connect(DB_PATH)
    try:
        df = pd.read_sql_query(query, conn, params=[start_date, end_date])
    except Exception:
        return _empty_frame()
    finally:
        conn.close()
    if df.empty:
        return _empty_frame()
    return df


def _load_derivatives_history_from_db(start_date: str, end_date: str) -> pd.DataFrame:
    query = (
        "SELECT date, source, funding_rate_daily, open_interest_value, "
        "perp_premium_daily, source_version "
        "FROM btc_derivatives_history WHERE date >= ? AND date <= ? ORDER BY date, source"
    )
    conn = duckdb.connect(DB_PATH)
    try:
        return pd.read_sql_query(query, conn, params=[start_date, end_date])
    except Exception:
        return pd.DataFrame(
            columns=[
                "date",
                "source",
                "funding_rate_daily",
                "open_interest_value",
                "perp_premium_daily",
                "source_version",
            ]
        )
    finally:
        conn.close()


def _fetch_wikipedia_views(session: requests.Session, start_date: str, end_date: str) -> pd.DataFrame:
    start_key = start_date.replace("-", "") + "00"
    end_key = end_date.replace("-", "") + "00"
    url = (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"en.wikipedia.org/all-access/all-agents/Bitcoin/daily/{start_key}/{end_key}"
    )
    payload = _request_json(session, url)
    rows = [
        {
            "date": datetime.strptime(item["timestamp"][:8], "%Y%m%d").strftime("%Y-%m-%d"),
            "wiki_views": float(item["views"]),
        }
        for item in payload.get("items", [])
    ]
    if not rows:
        return _empty_frame()
    return pd.DataFrame(rows).sort_values("date").drop_duplicates("date", keep="last")


def _fetch_fear_greed(session: requests.Session) -> pd.DataFrame:
    payload = _request_json(session, "https://api.alternative.me/fng/", params={"limit": 0})
    rows = [
        {
            "date": _epoch_to_date(item["timestamp"]),
            "fear_greed_value": float(item["value"]),
        }
        for item in payload.get("data", [])
    ]
    if not rows:
        return _empty_frame()
    return pd.DataFrame(rows).sort_values("date").drop_duplicates("date", keep="last")


def _fetch_blockchain_chart(session: requests.Session, chart_name: str, value_column: str) -> pd.DataFrame:
    payload = _request_json(
        session,
        f"https://api.blockchain.info/charts/{chart_name}",
        params={"timespan": "all", "format": "json", "sampled": "false"},
    )
    rows = [
        {
            "date": _epoch_to_date(item["x"]),
            value_column: float(item["y"]),
        }
        for item in payload.get("values", [])
    ]
    if not rows:
        return _empty_frame()
    return pd.DataFrame(rows).sort_values("date").drop_duplicates("date", keep="last")


def _download_yfinance_close(ticker: str, start_date: str, end_date: str) -> pd.Series:
    end_exclusive = yfinance_exclusive_end(pd.Timestamp(end_date).date())
    df = yf.download(
        ticker,
        start=start_date,
        end=end_exclusive,
        progress=False,
        auto_adjust=False,
        threads=False,
    )
    if df.empty:
        return pd.Series(dtype="float64")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    close_column = "Adj Close" if "Adj Close" in df.columns else "Close"
    series = df[close_column].astype(float)
    index = pd.to_datetime(series.index)
    if getattr(index, "tz", None) is not None:
        index = index.tz_localize(None)
    series.index = index
    return series.sort_index()


def _download_first_available_close(
    tickers: str | list[str],
    start_date: str,
    end_date: str,
    minimum_rows: int = 30,
) -> tuple[pd.Series, str | None]:
    ticker_list = [tickers] if isinstance(tickers, str) else list(tickers)
    last_error: Exception | None = None

    for ticker in ticker_list:
        try:
            series = _download_yfinance_close(ticker, start_date, end_date)
        except Exception as exc:  # pragma: no cover - network best effort
            last_error = exc
            continue
        if len(series) >= minimum_rows:
            return series, ticker

    if last_error is not None:
        raise last_error
    return pd.Series(dtype="float64"), None


def _normalize_us10y_series(series: pd.Series) -> pd.Series:
    cleaned = series.astype(float)
    median_value = cleaned.dropna().median()
    if pd.notna(median_value) and median_value > 20:
        cleaned = cleaned / 10.0
    return cleaned


def _frame_from_series(series: pd.Series, value_column: str) -> pd.DataFrame:
    if series.empty:
        return _empty_frame()
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(series.index).strftime("%Y-%m-%d"),
            value_column: series.to_numpy(),
        }
    )
    return frame.sort_values("date").drop_duplicates("date", keep="last")


def _fetch_macro_frames(start_date: str, end_date: str) -> list[pd.DataFrame]:
    frames = []
    try:
        dxy_close, dxy_source = _download_first_available_close(
            YFINANCE_TICKERS["dxy_close"],
            start_date,
            end_date,
        )
        if not dxy_close.empty:
            dxy_return_20d = dxy_close.pct_change(20)
            frames.append(
                pd.DataFrame(
                    {
                        "date": pd.to_datetime(dxy_close.index).strftime("%Y-%m-%d"),
                        "dxy_close": dxy_close.to_numpy(),
                        "dxy_return_20d": dxy_return_20d.to_numpy(),
                        "dxy_return_z_90d": _rolling_z(dxy_return_20d, 90, 30).to_numpy(),
                    }
                ).sort_values("date")
            )
            print(f"[market_features] dxy source: {dxy_source}")
    except Exception as exc:  # pragma: no cover - network best effort
        print(f"[market_features] dxy unavailable: {exc}")

    try:
        us10y_yield = _normalize_us10y_series(
            _download_yfinance_close(YFINANCE_TICKERS["us10y_yield"], start_date, end_date)
        )
        if not us10y_yield.empty:
            us10y_change_20d_bps = (us10y_yield - us10y_yield.shift(20)) * 100.0
            frames.append(
                pd.DataFrame(
                    {
                        "date": pd.to_datetime(us10y_yield.index).strftime("%Y-%m-%d"),
                        "us10y_yield": us10y_yield.to_numpy(),
                        "us10y_change_20d_bps": us10y_change_20d_bps.to_numpy(),
                        "us10y_change_z_90d": _rolling_z(us10y_change_20d_bps, 90, 30).to_numpy(),
                    }
                ).sort_values("date")
            )
    except Exception as exc:  # pragma: no cover - network best effort
        print(f"[market_features] us10y unavailable: {exc}")

    try:
        spx_close = _download_yfinance_close(YFINANCE_TICKERS["spx_close"], start_date, end_date)
        frame = _frame_from_series(spx_close, "spx_close")
        if not frame.empty:
            frames.append(frame)
    except Exception as exc:  # pragma: no cover - network best effort
        print(f"[market_features] spx unavailable: {exc}")

    return frames


def _compute_btc_spx_corr_frame(
    dates: pd.Series,
    btc_close: pd.Series,
    spx_close: pd.Series,
) -> pd.DataFrame:
    overlap = pd.DataFrame(
        {
            "date": dates.astype(str),
            "btc_close": btc_close.astype(float).to_numpy(),
            "spx_close": pd.to_numeric(spx_close, errors="coerce").to_numpy(),
        }
    ).dropna(subset=["spx_close"])
    if overlap.empty:
        return _empty_frame()

    overlap["btc_return_1d"] = overlap["btc_close"].pct_change()
    overlap["spx_return_1d"] = overlap["spx_close"].pct_change()
    overlap["btc_spx_corr_30d"] = overlap["btc_return_1d"].rolling(30, min_periods=15).corr(
        overlap["spx_return_1d"]
    )
    return overlap[["date", "btc_spx_corr_30d"]]


def fetch_non_derivative_frames(start_date: str, end_date: str) -> list[pd.DataFrame]:
    frames = []
    with requests.Session() as session:
        session.headers.update(HTTP_HEADERS)
        fetchers = [
            ("wikipedia", lambda: _fetch_wikipedia_views(session, start_date, end_date)),
            ("fear_greed", lambda: _fetch_fear_greed(session)),
            ("unique_addresses", lambda: _fetch_blockchain_chart(session, "n-unique-addresses", "unique_addresses")),
            ("tx_count", lambda: _fetch_blockchain_chart(session, "n-transactions", "tx_count")),
        ]
        for name, fetcher in fetchers:
            try:
                frame = fetcher()
                if not frame.empty:
                    frames.append(frame)
            except Exception as exc:  # pragma: no cover - network best effort
                print(f"[market_features] {name} unavailable: {exc}")
    frames.extend(fetch_macro_frames(start_date, end_date))
    return frames


def fetch_macro_frames(start_date: str, end_date: str) -> list[pd.DataFrame]:
    return _fetch_macro_frames(start_date, end_date)


def init_market_features_table(conn: duckdb.DuckDBPyConnection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS btc_market_features (
            date TEXT PRIMARY KEY
        )
        """
    )
    existing_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(btc_market_features)").fetchall()
    }
    for column, column_type in MARKET_FEATURE_COLUMNS.items():
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE btc_market_features ADD COLUMN {column} {column_type}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_market_features_version "
        "ON btc_market_features(feature_source_version)"
    )
    conn.commit()


def build_market_features(df_ohlcv: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = _normalize_ohlcv(df_ohlcv)
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)
    prev_close = close.shift(1)

    returns = close.pct_change()
    abs_return_1d = returns.abs()
    dollar_volume = close * volume

    amihud_illiquidity = abs_return_1d / dollar_volume.replace(0, np.nan)
    amihud_illiquidity_20d = amihud_illiquidity.rolling(20, min_periods=10).mean()
    amihud_z_90d = _rolling_z(amihud_illiquidity_20d, 90, 30)

    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    true_range_pct = true_range / close.replace(0, np.nan)
    range_baseline_20d = true_range_pct.rolling(20, min_periods=10).median()
    range_compression_20d = true_range_pct / range_baseline_20d.replace(0, np.nan)

    features = pd.DataFrame(
        {
            "date": pd.to_datetime(df.index).strftime("%Y-%m-%d"),
            "dollar_volume": dollar_volume,
            "abs_return_1d": abs_return_1d,
            "amihud_illiquidity": amihud_illiquidity,
            "amihud_illiquidity_20d": amihud_illiquidity_20d,
            "amihud_z_90d": amihud_z_90d,
            "true_range_pct": true_range_pct,
            "range_compression_20d": range_compression_20d,
        }
    ).reset_index(drop=True)

    start_date = features["date"].iloc[0]
    end_date = features["date"].iloc[-1]
    base_dates = features[["date"]].copy()

    for frame in fetch_non_derivative_frames(start_date, end_date):
        base_dates = base_dates.merge(frame.reset_index(drop=True), on="date", how="left")

    existing_feature_snapshot = _load_existing_feature_snapshot(start_date, end_date)
    if not existing_feature_snapshot.empty:
        base_dates = base_dates.merge(existing_feature_snapshot, on="date", how="left", suffixes=("", "_stored"))
        for column in PRESERVED_RAW_FEATURE_COLUMNS:
            stored_column = f"{column}_stored"
            if stored_column in base_dates.columns:
                base_dates[column] = base_dates[column].combine_first(base_dates[stored_column])
                base_dates = base_dates.drop(columns=[stored_column])

    derivatives_history_df = fetch_derivatives_history(start_date, end_date)
    stored_derivatives_history_df = _load_derivatives_history_from_db(start_date, end_date)
    if not stored_derivatives_history_df.empty:
        frames = [stored_derivatives_history_df]
        if not derivatives_history_df.empty:
            frames.append(derivatives_history_df)
        derivatives_history_df = (
            pd.concat(frames, ignore_index=True, sort=False)
            .sort_values(["date", "source"])
            .drop_duplicates(["date", "source"], keep="last")
        )
    derivatives_features_df = aggregate_derivatives_history(derivatives_history_df, base_dates["date"])
    if not derivatives_features_df.empty:
        base_dates = base_dates.merge(derivatives_features_df, on="date", how="left")

    features = features.merge(base_dates, on="date", how="left")
    if "spx_close" in features.columns:
        spx_corr_frame = _compute_btc_spx_corr_frame(features["date"], close.reset_index(drop=True), features["spx_close"])
        if not spx_corr_frame.empty:
            features = features.merge(spx_corr_frame, on="date", how="left")

    raw_ffill_columns = [
        "wiki_views",
        "fear_greed_value",
        "funding_rate_daily",
        "perp_premium_daily",
        "open_interest_value",
        "unique_addresses",
        "tx_count",
        "dxy_close",
        "dxy_return_20d",
        "dxy_return_z_90d",
        "us10y_yield",
        "us10y_change_20d_bps",
        "us10y_change_z_90d",
        "spx_close",
        "btc_spx_corr_30d",
    ]
    available_raw_columns = [column for column in raw_ffill_columns if column in features.columns]
    if available_raw_columns:
        features[available_raw_columns] = features[available_raw_columns].ffill()

    if "wiki_views" in features:
        features["wiki_views_7d"] = features["wiki_views"].rolling(7, min_periods=3).mean()
        features["wiki_views_z_30d"] = _rolling_z(features["wiki_views_7d"], 30, 10)
    if "fear_greed_value" in features:
        features["fear_greed_z_30d"] = _rolling_z(features["fear_greed_value"], 30, 10)
    if "funding_rate_daily" in features and "funding_rate_z_30d" not in features.columns:
        features["funding_rate_z_30d"] = _rolling_z(features["funding_rate_daily"], 30, 10)
    elif "funding_rate_daily" in features and features["funding_rate_z_30d"].isna().all():
        features["funding_rate_z_30d"] = _rolling_z(features["funding_rate_daily"], 30, 10)
    if "perp_premium_daily" in features and "perp_premium_z_30d" not in features.columns:
        features["perp_premium_z_30d"] = _rolling_z(features["perp_premium_daily"], 30, 10)
    elif "perp_premium_daily" in features and features["perp_premium_z_30d"].isna().all():
        features["perp_premium_z_30d"] = _rolling_z(features["perp_premium_daily"], 30, 10)
    if "open_interest_value" in features and "open_interest_z_30d" not in features.columns:
        features["open_interest_z_30d"] = _rolling_z(features["open_interest_value"], 30, 10)
    elif "open_interest_value" in features and features["open_interest_z_30d"].isna().all():
        features["open_interest_z_30d"] = _rolling_z(features["open_interest_value"], 30, 10)
    if "open_interest_z_30d" in features:
        features["open_interest_z_30d"] = features["open_interest_z_30d"].ffill()
    if "open_interest_value" in features:
        features["open_interest_delta_1d"] = features["open_interest_value"].pct_change()
        features["open_interest_delta_z_30d"] = _rolling_z(features["open_interest_delta_1d"], 30, 10)
    if "unique_addresses" in features:
        features["unique_addresses_z_30d"] = _rolling_z(features["unique_addresses"], 30, 10)
    if "tx_count" in features:
        features["tx_count_z_30d"] = _rolling_z(features["tx_count"], 30, 10)

    onchain_inputs = [
        column
        for column in ["unique_addresses_z_30d", "tx_count_z_30d"]
        if column in features.columns
    ]
    if onchain_inputs:
        features["onchain_activity_z_30d"] = features[onchain_inputs].mean(axis=1, skipna=True)

    price_return_1d = close.pct_change().reset_index(drop=True)
    price_return_3d = close.pct_change(3).reset_index(drop=True)
    if "open_interest_delta_1d" in features:
        oi_delta = features["open_interest_delta_1d"]
        conditions = [
            (oi_delta > 0) & (price_return_1d > 0),
            (oi_delta > 0) & (price_return_1d < 0),
            (oi_delta < 0) & (price_return_1d > 0),
            (oi_delta < 0) & (price_return_1d < 0),
            (oi_delta == 0),
        ]
        choices = ["long_build", "short_build", "short_cover", "long_unwind", "unchanged"]
        features["oi_price_state_1d"] = np.select(conditions, choices, default=None)

    if "funding_rate_z_30d" in features:
        funding_z = pd.to_numeric(features["funding_rate_z_30d"], errors="coerce")
        mismatch_mask = (
            funding_z.notna()
            & price_return_3d.notna()
            & (np.sign(funding_z) * np.sign(price_return_3d) < 0)
        )
        features["funding_price_divergence_3d"] = pd.Series(
            np.where(mismatch_mask, np.abs(funding_z), -np.abs(funding_z)),
            index=features.index,
            dtype="float64",
        )
        features["funding_contrarian_bias_3d"] = pd.Series(
            np.select(
                [
                    (price_return_3d > 0) & (funding_z < 0),
                    (price_return_3d < 0) & (funding_z > 0),
                ],
                [1, -1],
                default=0,
            ),
            index=features.index,
            dtype="int64",
        )

    for column in MARKET_FEATURE_COLUMNS:
        if column not in features.columns:
            features[column] = np.nan

    features["feature_source_version"] = FEATURE_SOURCE_VERSION
    features = features[list(MARKET_FEATURE_COLUMNS.keys())]
    return features.replace({np.nan: None}), derivatives_history_df.replace({np.nan: None})


def save_market_features_to_db(conn: duckdb.DuckDBPyConnection, features_df: pd.DataFrame):
    init_market_features_table(conn)
    columns = list(MARKET_FEATURE_COLUMNS.keys())
    records = [tuple(row[column] for column in columns) for _, row in features_df.iterrows()]
    placeholders = ", ".join(["?"] * len(columns))
    column_sql = ", ".join(columns)
    conn.executemany(
        f"""
        INSERT INTO btc_market_features ({column_sql})
        VALUES ({placeholders})
        ON CONFLICT (date) DO UPDATE SET
        {', '.join(f'{c}=EXCLUDED.{c}' for c in columns if c != 'date')}
        """,
        records,
    )
    conn.commit()


def load_daily_from_db(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT date, open, high, low, close, volume FROM btc_daily ORDER BY date",
        conn,
        parse_dates=["date"],
    )
    if df.empty:
        raise RuntimeError("Table btc_daily is empty. Run research/main.py first.")
    return df.set_index("date")


def main():
    conn = duckdb.connect(DB_PATH)
    try:
        daily_df = load_daily_from_db(conn)
        features_df, derivatives_history_df = build_market_features(daily_df)
        save_market_features_to_db(conn, features_df)
        save_derivatives_history_to_db(conn, derivatives_history_df)
    finally:
        conn.close()

    print(
        "btc_market_features updated:",
        len(features_df),
        features_df["date"].iloc[0],
        "->",
        features_df["date"].iloc[-1],
    )
    print("btc_derivatives_history rows:", len(derivatives_history_df))


if __name__ == "__main__":
    main()
