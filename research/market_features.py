"""Market feature engineering for BTC daily data."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

from astro_shared import DB_PATH


FEATURE_SOURCE_VERSION = "market_features_v2"
HTTP_TIMEOUT = 30
HTTP_HEADERS = {
    "User-Agent": "AstroBTC/1.0 (market feature pipeline)",
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
    "perp_premium_daily": "REAL",
    "perp_premium_z_30d": "REAL",
    "open_interest_value": "REAL",
    "open_interest_z_30d": "REAL",
    "unique_addresses": "REAL",
    "unique_addresses_z_30d": "REAL",
    "tx_count": "REAL",
    "tx_count_z_30d": "REAL",
    "onchain_activity_z_30d": "REAL",
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


def _request_json(session: requests.Session, url: str, params: dict | None = None) -> dict:
    response = session.get(url, params=params, timeout=HTTP_TIMEOUT, headers=HTTP_HEADERS)
    response.raise_for_status()
    return response.json()


def _date_to_epoch_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _epoch_ms_to_date(epoch_ms: int | str) -> str:
    return datetime.fromtimestamp(int(epoch_ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _epoch_to_date(epoch_seconds: int | str) -> str:
    return datetime.fromtimestamp(int(epoch_seconds), tz=timezone.utc).strftime("%Y-%m-%d")


def _rolling_z(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    mean_series = series.rolling(window, min_periods=min_periods).mean()
    std_series = series.rolling(window, min_periods=min_periods).std(ddof=0)
    return (series - mean_series) / std_series.replace(0, np.nan)


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame({"date": pd.Series(dtype="object")})


def _fetch_wikipedia_views(session: requests.Session, start_date: str, end_date: str) -> pd.DataFrame:
    start_key = start_date.replace("-", "") + "00"
    end_key = end_date.replace("-", "") + "00"
    url = (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"en.wikipedia.org/all-access/all-agents/Bitcoin/daily/{start_key}/{end_key}"
    )
    payload = _request_json(session, url)
    rows = []
    for item in payload.get("items", []):
        rows.append(
            {
                "date": datetime.strptime(item["timestamp"][:8], "%Y%m%d").strftime("%Y-%m-%d"),
                "wiki_views": float(item["views"]),
            }
        )
    if not rows:
        return _empty_frame()
    return pd.DataFrame(rows).sort_values("date").drop_duplicates("date", keep="last")


def _fetch_fear_greed(session: requests.Session) -> pd.DataFrame:
    payload = _request_json(session, "https://api.alternative.me/fng/", params={"limit": 0})
    rows = []
    for item in payload.get("data", []):
        rows.append(
            {
                "date": _epoch_to_date(item["timestamp"]),
                "fear_greed_value": float(item["value"]),
            }
        )
    if not rows:
        return _empty_frame()
    return pd.DataFrame(rows).sort_values("date").drop_duplicates("date", keep="last")


def _paginate_okx_records(
    session: requests.Session,
    url: str,
    params: dict,
    timestamp_getter,
    start_ms: int,
    limit: int = 100,
    sleep_seconds: float = 0.12,
) -> list:
    cursor = None
    records = []

    for _ in range(300):
        page_params = dict(params)
        page_params["limit"] = limit
        if cursor is not None:
            page_params["after"] = cursor

        payload = _request_json(session, url, params=page_params)
        page = payload.get("data", [])
        if not page:
            break

        records.extend(page)
        oldest_ts = min(int(timestamp_getter(item)) for item in page)
        if oldest_ts <= start_ms:
            break
        cursor = oldest_ts
        time.sleep(sleep_seconds)

    return records


def _fetch_okx_funding(session: requests.Session, start_date: str) -> pd.DataFrame:
    url = "https://www.okx.com/api/v5/public/funding-rate-history"
    start_ms = _date_to_epoch_ms(start_date)
    records = _paginate_okx_records(
        session,
        url,
        {"instId": "BTC-USDT-SWAP"},
        lambda item: item["fundingTime"],
        start_ms,
    )
    if not records:
        return _empty_frame()

    rows = []
    for item in records:
        rows.append(
            {
                "date": _epoch_ms_to_date(item["fundingTime"]),
                "funding_rate_daily": float(item.get("realizedRate") or item.get("fundingRate") or 0.0),
            }
        )
    df = pd.DataFrame(rows)
    df = df.groupby("date", as_index=False)["funding_rate_daily"].sum()
    return df.sort_values("date")


def _fetch_okx_candles(
    session: requests.Session,
    url: str,
    params: dict,
    start_date: str,
) -> pd.DataFrame:
    start_ms = _date_to_epoch_ms(start_date)
    records = _paginate_okx_records(
        session,
        url,
        params,
        lambda item: item[0],
        start_ms,
    )
    if not records:
        return _empty_frame()

    rows = []
    for item in records:
        rows.append(
            {
                "date": _epoch_ms_to_date(item[0]),
                "close": float(item[4]),
            }
        )
    return pd.DataFrame(rows).sort_values("date").drop_duplicates("date", keep="last")


def _fetch_okx_perp_premium(session: requests.Session, start_date: str) -> pd.DataFrame:
    mark_df = _fetch_okx_candles(
        session,
        "https://www.okx.com/api/v5/market/history-mark-price-candles",
        {"instId": "BTC-USDT-SWAP", "bar": "1D"},
        start_date,
    ).rename(columns={"close": "mark_close"})
    index_df = _fetch_okx_candles(
        session,
        "https://www.okx.com/api/v5/market/history-index-candles",
        {"instId": "BTC-USDT", "bar": "1D"},
        start_date,
    ).rename(columns={"close": "index_close"})

    if mark_df.empty or index_df.empty:
        return _empty_frame()

    df = mark_df.merge(index_df, on="date", how="inner")
    df["perp_premium_daily"] = df["mark_close"] / df["index_close"].replace(0, np.nan) - 1.0
    return df[["date", "perp_premium_daily"]].sort_values("date")


def _fetch_okx_open_interest(session: requests.Session) -> pd.DataFrame:
    payload = _request_json(
        session,
        "https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume",
        params={"ccy": "BTC", "period": "1D"},
    )
    rows = []
    for item in payload.get("data", []):
        rows.append(
            {
                "date": _epoch_ms_to_date(item[0]),
                "open_interest_value": float(item[1]),
            }
        )
    if not rows:
        return _empty_frame()
    return pd.DataFrame(rows).sort_values("date").drop_duplicates("date", keep="last")


def _fetch_blockchain_chart(session: requests.Session, chart_name: str, value_column: str) -> pd.DataFrame:
    payload = _request_json(
        session,
        f"https://api.blockchain.info/charts/{chart_name}",
        params={"timespan": "all", "format": "json", "sampled": "false"},
    )
    rows = []
    for item in payload.get("values", []):
        rows.append(
            {
                "date": _epoch_to_date(item["x"]),
                value_column: float(item["y"]),
            }
        )
    if not rows:
        return _empty_frame()
    return pd.DataFrame(rows).sort_values("date").drop_duplicates("date", keep="last")


def fetch_external_feature_frames(start_date: str, end_date: str) -> list[pd.DataFrame]:
    frames = []
    with requests.Session() as session:
        session.headers.update(HTTP_HEADERS)
        fetchers = [
            ("wikipedia", lambda: _fetch_wikipedia_views(session, start_date, end_date)),
            ("fear_greed", lambda: _fetch_fear_greed(session)),
            ("funding", lambda: _fetch_okx_funding(session, start_date)),
            ("perp_premium", lambda: _fetch_okx_perp_premium(session, start_date)),
            ("open_interest", lambda: _fetch_okx_open_interest(session)),
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

    return frames


def init_market_features_table(conn: sqlite3.Connection):
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
            conn.execute(
                f"ALTER TABLE btc_market_features ADD COLUMN {column} {column_type}"
            )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_market_features_version "
        "ON btc_market_features(feature_source_version)"
    )
    conn.commit()


def build_market_features(df_ohlcv: pd.DataFrame) -> pd.DataFrame:
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
    base_dates = features[["date"]].copy().reset_index(drop=True)
    for frame in fetch_external_feature_frames(start_date, end_date):
        base_dates = base_dates.merge(frame.reset_index(drop=True), on="date", how="left")

    features = features.merge(base_dates, on="date", how="left")
    external_raw_columns = [
        "wiki_views",
        "fear_greed_value",
        "funding_rate_daily",
        "perp_premium_daily",
        "open_interest_value",
        "unique_addresses",
        "tx_count",
    ]
    available_raw_columns = [column for column in external_raw_columns if column in features.columns]
    if available_raw_columns:
        features[available_raw_columns] = features[available_raw_columns].ffill()

    if "wiki_views" in features:
        features["wiki_views_7d"] = features["wiki_views"].rolling(7, min_periods=3).mean()
        features["wiki_views_z_30d"] = _rolling_z(features["wiki_views_7d"], 30, 10)
    if "fear_greed_value" in features:
        features["fear_greed_z_30d"] = _rolling_z(features["fear_greed_value"], 30, 10)
    if "funding_rate_daily" in features:
        features["funding_rate_z_30d"] = _rolling_z(features["funding_rate_daily"], 30, 10)
    if "perp_premium_daily" in features:
        features["perp_premium_z_30d"] = _rolling_z(features["perp_premium_daily"], 30, 10)
    if "open_interest_value" in features:
        features["open_interest_z_30d"] = _rolling_z(features["open_interest_value"], 30, 10)
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

    for column in MARKET_FEATURE_COLUMNS:
        if column not in features.columns:
            features[column] = np.nan

    features["feature_source_version"] = FEATURE_SOURCE_VERSION
    features = features[list(MARKET_FEATURE_COLUMNS.keys())]
    return features.replace({np.nan: None})


def save_market_features_to_db(conn: sqlite3.Connection, features_df: pd.DataFrame):
    init_market_features_table(conn)
    columns = list(MARKET_FEATURE_COLUMNS.keys())
    records = [
        tuple(row[column] for column in columns)
        for _, row in features_df.iterrows()
    ]
    placeholders = ", ".join(["?"] * len(columns))
    column_sql = ", ".join(columns)
    conn.executemany(
        f"""
        INSERT OR REPLACE INTO btc_market_features ({column_sql})
        VALUES ({placeholders})
        """,
        records,
    )
    conn.commit()


def load_daily_from_db(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT date, open, high, low, close, volume FROM btc_daily ORDER BY date",
        conn,
        parse_dates=["date"],
    )
    if df.empty:
        raise RuntimeError("Table btc_daily is empty. Run research/main.py first.")
    return df.set_index("date")


def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        daily_df = load_daily_from_db(conn)
        features_df = build_market_features(daily_df)
        save_market_features_to_db(conn, features_df)
    finally:
        conn.close()

    print(
        "btc_market_features updated:",
        len(features_df),
        features_df["date"].iloc[0],
        "->",
        features_df["date"].iloc[-1],
    )


if __name__ == "__main__":
    main()
