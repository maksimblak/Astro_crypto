"""Historical derivatives sources and aggregation for BTC market features."""

from __future__ import annotations

import io
import duckdb
import time
import zipfile
from datetime import datetime, timezone

import pandas as pd
import requests


DERIVATIVES_SOURCE_VERSION = "derivatives_history_v1"
HTTP_TIMEOUT = 30
HTTP_HEADERS = {
    "User-Agent": "AstroBTC/1.0 (derivatives history pipeline)",
}
OI_PRIMARY_SOURCE_PRIORITY = ["bybit", "okx"]


def _request_json(session: requests.Session, url: str, params: dict | None = None):
    response = session.get(url, params=params, timeout=HTTP_TIMEOUT, headers=HTTP_HEADERS)
    response.raise_for_status()
    return response.json()


def _date_to_epoch_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _epoch_ms_to_date(epoch_ms: int | str) -> str:
    return datetime.fromtimestamp(int(epoch_ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _rolling_z(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    mean_series = series.rolling(window, min_periods=min_periods).mean()
    std_series = series.rolling(window, min_periods=min_periods).std(ddof=0)
    return (series - mean_series) / std_series.replace(0, pd.NA)


def _first_valid(series: pd.Series):
    valid = series.dropna()
    return valid.iloc[-1] if not valid.empty else None


def _month_iter(start_date: str, end_date: str) -> list[str]:
    start = pd.Timestamp(start_date).to_period("M")
    end = pd.Timestamp(end_date).to_period("M")
    months = []
    current = start
    while current <= end:
        months.append(str(current))
        current += 1
    return months


def init_derivatives_history_table(conn: duckdb.DuckDBPyConnection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS btc_derivatives_history (
            date TEXT NOT NULL,
            source TEXT NOT NULL,
            funding_rate_daily REAL,
            open_interest_value REAL,
            perp_premium_daily REAL,
            source_version TEXT,
            PRIMARY KEY (date, source)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_derivatives_history_source "
        "ON btc_derivatives_history(source)"
    )
    conn.commit()


def save_derivatives_history_to_db(conn: duckdb.DuckDBPyConnection, derivatives_df: pd.DataFrame):
    if derivatives_df.empty:
        return

    init_derivatives_history_table(conn)
    records = [
        (
            row["date"],
            row["source"],
            row.get("funding_rate_daily"),
            row.get("open_interest_value"),
            row.get("perp_premium_daily"),
            row.get("source_version"),
        )
        for _, row in derivatives_df.iterrows()
    ]
    conn.executemany(
        """
        INSERT OR REPLACE INTO btc_derivatives_history (
            date,
            source,
            funding_rate_daily,
            open_interest_value,
            perp_premium_daily,
            source_version
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        records,
    )
    conn.commit()


def _paginate_okx(session: requests.Session, url: str, params: dict, timestamp_getter, start_ms: int) -> list:
    cursor = None
    records = []
    for _ in range(300):
        page_params = dict(params)
        page_params["limit"] = 100
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
        time.sleep(0.12)
    return records


def _fetch_okx_derivatives(session: requests.Session, start_date: str) -> list[pd.DataFrame]:
    start_ms = _date_to_epoch_ms(start_date)
    frames = []

    funding_records = _paginate_okx(
        session,
        "https://www.okx.com/api/v5/public/funding-rate-history",
        {"instId": "BTC-USDT-SWAP"},
        lambda item: item["fundingTime"],
        start_ms,
    )
    if funding_records:
        funding_rows = [
            {
                "date": _epoch_ms_to_date(item["fundingTime"]),
                "source": "okx",
                "funding_rate_daily": float(item.get("realizedRate") or item.get("fundingRate") or 0.0),
            }
            for item in funding_records
        ]
        funding_df = pd.DataFrame(funding_rows)
        funding_df = funding_df.groupby(["date", "source"], as_index=False)["funding_rate_daily"].sum()
        frames.append(funding_df)

    oi_payload = _request_json(
        session,
        "https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume",
        params={"ccy": "BTC", "period": "1D"},
    )
    oi_rows = [
        {
            "date": _epoch_ms_to_date(item[0]),
            "source": "okx",
            "open_interest_value": float(item[1]),
        }
        for item in oi_payload.get("data", [])
    ]
    if oi_rows:
        frames.append(pd.DataFrame(oi_rows))

    mark_records = _paginate_okx(
        session,
        "https://www.okx.com/api/v5/market/history-mark-price-candles",
        {"instId": "BTC-USDT-SWAP", "bar": "1D"},
        lambda item: item[0],
        start_ms,
    )
    index_records = _paginate_okx(
        session,
        "https://www.okx.com/api/v5/market/history-index-candles",
        {"instId": "BTC-USDT", "bar": "1D"},
        lambda item: item[0],
        start_ms,
    )
    if mark_records and index_records:
        mark_df = pd.DataFrame(
            [{"date": _epoch_ms_to_date(item[0]), "mark_close": float(item[4])} for item in mark_records]
        ).drop_duplicates("date", keep="last")
        index_df = pd.DataFrame(
            [{"date": _epoch_ms_to_date(item[0]), "index_close": float(item[4])} for item in index_records]
        ).drop_duplicates("date", keep="last")
        premium_df = mark_df.merge(index_df, on="date", how="inner")
        premium_df["perp_premium_daily"] = premium_df["mark_close"] / premium_df["index_close"].replace(0, pd.NA) - 1.0
        premium_df["source"] = "okx"
        frames.append(premium_df[["date", "source", "perp_premium_daily"]])

    return frames


def _fetch_bitmex_funding(session: requests.Session, start_date: str) -> pd.DataFrame:
    start_ts = pd.Timestamp(start_date, tz="UTC")
    rows = []
    start_offset = 0
    page_size = 500

    for _ in range(200):
        payload = _request_json(
            session,
            "https://www.bitmex.com/api/v1/funding",
            params={
                "symbol": "XBTUSD",
                "count": page_size,
                "start": start_offset,
                "reverse": "true",
            },
        )
        if not payload:
            break

        for item in payload:
            ts = pd.Timestamp(item["timestamp"], tz="UTC")
            if ts < start_ts:
                continue
            rows.append(
                {
                    "date": ts.strftime("%Y-%m-%d"),
                    "source": "bitmex",
                    "funding_rate_daily": float(item.get("fundingRateDaily") or 0.0),
                }
            )

        oldest_ts = min(pd.Timestamp(item["timestamp"], tz="UTC") for item in payload)
        if oldest_ts < start_ts or len(payload) < page_size:
            break

        start_offset += len(payload)
        time.sleep(0.12)

    if not rows:
        return pd.DataFrame(columns=["date", "source", "funding_rate_daily"])
    df = pd.DataFrame(rows)
    return df.groupby(["date", "source"], as_index=False)["funding_rate_daily"].sum()


def _fetch_bybit_open_interest(session: requests.Session, start_date: str) -> pd.DataFrame:
    start_ms = _date_to_epoch_ms(start_date)
    cursor = None
    rows = []

    for _ in range(400):
        params = {
            "category": "linear",
            "symbol": "BTCUSDT",
            "intervalTime": "1d",
            "limit": 200,
        }
        if cursor:
            params["cursor"] = cursor
        payload = _request_json(session, "https://api.bybit.com/v5/market/open-interest", params=params)
        page = payload.get("result", {}).get("list", [])
        if not page:
            break

        for item in page:
            ts = int(item["timestamp"])
            if ts < start_ms:
                continue
            rows.append(
                {
                    "date": _epoch_ms_to_date(ts),
                    "source": "bybit",
                    "open_interest_value": float(item["openInterest"]),
                }
            )

        oldest_ts = min(int(item["timestamp"]) for item in page)
        if oldest_ts < start_ms:
            break

        cursor = payload.get("result", {}).get("nextPageCursor")
        if not cursor:
            break
        time.sleep(0.12)

    if not rows:
        return pd.DataFrame(columns=["date", "source", "open_interest_value"])
    return pd.DataFrame(rows).drop_duplicates(["date", "source"], keep="last")


def _fetch_bybit_funding(session: requests.Session, start_date: str) -> pd.DataFrame:
    start_ms = _date_to_epoch_ms(start_date)
    end_ms = int(pd.Timestamp.utcnow().timestamp() * 1000)
    rows = []

    for _ in range(300):
        payload = _request_json(
            session,
            "https://api.bybit.com/v5/market/funding/history",
            params={
                "category": "linear",
                "symbol": "BTCUSDT",
                "limit": 200,
                "endTime": end_ms,
            },
        )
        page = payload.get("result", {}).get("list", [])
        if not page:
            break

        for item in page:
            ts = int(item["fundingRateTimestamp"])
            if ts < start_ms:
                continue
            rows.append(
                {
                    "date": _epoch_ms_to_date(ts),
                    "source": "bybit",
                    "funding_rate_daily": float(item["fundingRate"]),
                }
            )

        oldest_ts = min(int(item["fundingRateTimestamp"]) for item in page)
        if oldest_ts < start_ms:
            break
        end_ms = oldest_ts - 1
        time.sleep(0.12)

    if not rows:
        return pd.DataFrame(columns=["date", "source", "funding_rate_daily"])
    df = pd.DataFrame(rows)
    return df.groupby(["date", "source"], as_index=False)["funding_rate_daily"].sum()


def _fetch_binance_archive_funding(session: requests.Session, start_date: str, end_date: str) -> pd.DataFrame:
    # Binance USD-M funding data only exists from the futures launch onward.
    effective_start = max(pd.Timestamp(start_date), pd.Timestamp("2019-09-01"))
    rows = []

    for month_key in _month_iter(effective_start.strftime("%Y-%m-%d"), end_date):
        url = (
            "https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/"
            f"BTCUSDT-fundingRate-{month_key}.zip"
        )
        try:
            response = session.get(url, timeout=HTTP_TIMEOUT, headers=HTTP_HEADERS)
            if response.status_code == 404:
                continue
            response.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                names = archive.namelist()
                if not names:
                    continue
                with archive.open(names[0]) as handle:
                    month_df = pd.read_csv(handle)
        except Exception:
            continue

        if month_df.empty:
            continue
        month_df["date"] = pd.to_datetime(month_df["calc_time"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
        month_df["funding_rate_daily"] = month_df["last_funding_rate"].astype(float)
        month_df["source"] = "binance_archive"
        rows.append(month_df[["date", "source", "funding_rate_daily"]])
        time.sleep(0.08)

    if not rows:
        return pd.DataFrame(columns=["date", "source", "funding_rate_daily"])
    df = pd.concat(rows, ignore_index=True)
    return df.groupby(["date", "source"], as_index=False)["funding_rate_daily"].sum()


def fetch_derivatives_history(start_date: str, end_date: str) -> pd.DataFrame:
    frames = []
    with requests.Session() as session:
        session.headers.update(HTTP_HEADERS)
        fetchers = [
            ("okx_derivatives", lambda: _fetch_okx_derivatives(session, start_date)),
            ("bitmex_funding", lambda: [_fetch_bitmex_funding(session, start_date)]),
            ("bybit_open_interest", lambda: [_fetch_bybit_open_interest(session, start_date)]),
            ("bybit_funding", lambda: [_fetch_bybit_funding(session, start_date)]),
            ("binance_archive_funding", lambda: [_fetch_binance_archive_funding(session, start_date, end_date)]),
        ]

        for name, fetcher in fetchers:
            try:
                source_frames = fetcher()
                for frame in source_frames:
                    if not frame.empty:
                        frames.append(frame)
            except Exception as exc:  # pragma: no cover - network best effort
                print(f"[derivatives_history] {name} unavailable: {exc}")

    if not frames:
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

    history_df = pd.concat(frames, ignore_index=True, sort=False)
    history_df["source_version"] = DERIVATIVES_SOURCE_VERSION
    history_df = (
        history_df.sort_values(["date", "source"])
        .groupby(["date", "source"], as_index=False)
        .agg(
            {
                "funding_rate_daily": lambda s: s.dropna().sum() if not s.dropna().empty else None,
                "open_interest_value": _first_valid,
                "perp_premium_daily": _first_valid,
                "source_version": _first_valid,
            }
        )
    )
    return history_df


def aggregate_derivatives_history(history_df: pd.DataFrame, base_dates: pd.Series) -> pd.DataFrame:
    aggregate_df = pd.DataFrame({"date": base_dates.astype(str).tolist()})
    if history_df.empty:
        return aggregate_df

    funding_pivot = history_df.pivot_table(
        index="date",
        columns="source",
        values="funding_rate_daily",
        aggfunc="sum",
    ).sort_index()
    if not funding_pivot.empty:
        funding_df = pd.DataFrame(
            {
                "date": funding_pivot.index.astype(str),
                "funding_rate_daily": funding_pivot.median(axis=1, skipna=True).to_numpy(),
                "funding_source_count": funding_pivot.notna().sum(axis=1).to_numpy(),
            }
        ).reset_index(drop=True)
        aggregate_df = aggregate_df.merge(funding_df, on="date", how="left")

    oi_pivot = history_df.pivot_table(
        index="date",
        columns="source",
        values="open_interest_value",
        aggfunc="last",
    ).sort_index()
    if not oi_pivot.empty:
        oi_z_frames = []
        for source in oi_pivot.columns:
            source_series = oi_pivot[source].ffill(limit=3)
            oi_z_frames.append(_rolling_z(source_series, 30, 10).rename(source))
        oi_z_df = pd.concat(oi_z_frames, axis=1) if oi_z_frames else pd.DataFrame(index=oi_pivot.index)

        primary_value = pd.Series(index=oi_pivot.index, dtype="float64")
        primary_source = pd.Series(index=oi_pivot.index, dtype="object")
        for source in OI_PRIMARY_SOURCE_PRIORITY + [src for src in oi_pivot.columns if src not in OI_PRIMARY_SOURCE_PRIORITY]:
            if source not in oi_pivot.columns:
                continue
            mask = primary_value.isna() & oi_pivot[source].notna()
            primary_value.loc[mask] = oi_pivot.loc[mask, source]
            primary_source.loc[mask] = source

        oi_df = pd.DataFrame(
            {
                "date": oi_pivot.index.astype(str),
                "open_interest_value": primary_value.to_numpy(),
                "open_interest_primary_source": primary_source.to_numpy(),
                "open_interest_source_count": oi_pivot.notna().sum(axis=1).to_numpy(),
                "open_interest_z_30d": (
                    oi_z_df.median(axis=1, skipna=True).to_numpy()
                    if not oi_z_df.empty
                    else pd.Series(index=oi_pivot.index, dtype="float64").to_numpy()
                ),
            }
        ).reset_index(drop=True)
        aggregate_df = aggregate_df.merge(oi_df, on="date", how="left")

    premium_pivot = history_df.pivot_table(
        index="date",
        columns="source",
        values="perp_premium_daily",
        aggfunc="last",
    ).sort_index()
    if not premium_pivot.empty:
        premium_df = pd.DataFrame(
            {
                "date": premium_pivot.index.astype(str),
                "perp_premium_daily": premium_pivot.median(axis=1, skipna=True).to_numpy(),
                "perp_premium_source_count": premium_pivot.notna().sum(axis=1).to_numpy(),
            }
        ).reset_index(drop=True)
        aggregate_df = aggregate_df.merge(premium_df, on="date", how="left")

    aggregate_df["derivatives_source_version"] = DERIVATIVES_SOURCE_VERSION
    return aggregate_df
