"""BTC macro cycle metrics for top/bottom monitoring."""

from __future__ import annotations

import os
import time

import duckdb
import numpy as np
import pandas as pd
import requests

try:
    from .config import DB_PATH, HTTP_MAX_RETRIES, HTTP_TIMEOUT, HTTP_USER_AGENT
except ImportError:
    from config import DB_PATH, HTTP_MAX_RETRIES, HTTP_TIMEOUT, HTTP_USER_AGENT


CYCLE_SOURCE_VERSION = "cycle_metrics_v1"
BGEOMETRICS_BASE_URL = "https://bitcoin-data.com"
BGEOMETRICS_TOKEN_ENV = "ASTROBTC_BGEOMETRICS_TOKEN"
CYCLE_WINDOW_DAYS = 1460
CYCLE_MIN_PERIODS = 365

BGEOMETRICS_METRICS = {
    "mvrv_zscore": ("/v1/mvrv-zscore", "mvrvZscore"),
    "nupl": ("/v1/nupl", "nupl"),
    "puell_multiple": ("/v1/puell-multiple", "puellMultiple"),
    "hashribbons": ("/v1/hashribbons", "hashribbons"),
}

CYCLE_METRIC_COLUMNS = {
    "date": "TEXT PRIMARY KEY",
    "price": "REAL",
    "mvrv_zscore": "REAL",
    "nupl": "REAL",
    "puell_multiple": "REAL",
    "pi_sma111": "REAL",
    "pi_sma350x2": "REAL",
    "pi_cycle_signal": "INTEGER",
    "hashrate_sma_30": "REAL",
    "hashrate_sma_60": "REAL",
    "hashribbon_trend": "TEXT",
    "hashribbon_buy_signal": "INTEGER",
    "hashribbon_sell_signal": "INTEGER",
    "mvrv_top_threshold": "REAL",
    "nupl_top_threshold": "REAL",
    "puell_top_threshold": "REAL",
    "mvrv_bottom_extreme": "REAL",
    "nupl_bottom_extreme": "REAL",
    "puell_bottom_extreme": "REAL",
    "mvrv_top_score": "REAL",
    "mvrv_bottom_score": "REAL",
    "nupl_top_score": "REAL",
    "nupl_bottom_score": "REAL",
    "puell_top_score": "REAL",
    "puell_bottom_score": "REAL",
    "pi_cycle_top_score": "REAL",
    "pi_cycle_bottom_score": "REAL",
    "hashribbon_bottom_score": "REAL",
    "top_score": "REAL",
    "bottom_score": "REAL",
    "cycle_bias": "REAL",
    "cycle_zone": "TEXT",
    "source_version": "TEXT",
}

PRESERVED_REMOTE_COLUMNS = [
    "mvrv_zscore",
    "nupl",
    "puell_multiple",
    "hashrate_sma_30",
    "hashrate_sma_60",
    "hashribbon_trend",
]


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {}
    for column in df.columns:
        lowered = str(column).lower()
        if lowered in {"open", "high", "low", "close", "volume"}:
            rename_map[column] = lowered
    normalized = df.rename(columns=rename_map).copy()
    required = ["close"]
    missing = [column for column in required if column not in normalized.columns]
    if missing:
        raise ValueError(f"Missing OHLCV columns: {missing}")
    return normalized


def _request_json(
    session: requests.Session,
    url: str,
    params: dict[str, str] | None = None,
    max_retries: int = HTTP_MAX_RETRIES,
):
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = session.get(
                url,
                params=params,
                timeout=HTTP_TIMEOUT,
                headers={"User-Agent": HTTP_USER_AGENT},
            )
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
        except requests.HTTPError:
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"Failed to fetch {url}")


def _extract_records(payload) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        if "d" in payload:
            return [payload]

        for key in ("items", "content", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        embedded = payload.get("_embedded")
        if isinstance(embedded, dict):
            for value in embedded.values():
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]

    return []


def _fetch_bgeometrics_series(
    session: requests.Session,
    path: str,
    value_keys: dict[str, str],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    params = {"startday": start_date, "endday": end_date}
    token = os.getenv(BGEOMETRICS_TOKEN_ENV)
    if token:
        params["token"] = token

    payload = _request_json(session, f"{BGEOMETRICS_BASE_URL}{path}", params=params)
    rows = _extract_records(payload)
    if not rows:
        return pd.DataFrame(columns=["date", *value_keys.keys()])

    frame = pd.DataFrame(rows)
    if "d" not in frame.columns:
        return pd.DataFrame(columns=["date", *value_keys.keys()])

    result = pd.DataFrame({"date": frame["d"].astype(str)})
    for target_column, source_column in value_keys.items():
        if source_column not in frame.columns:
            result[target_column] = np.nan
            continue
        result[target_column] = pd.to_numeric(frame[source_column], errors="coerce")

    return result.sort_values("date").drop_duplicates("date", keep="last")


def _fetch_remote_cycle_frames(start_date: str, end_date: str) -> list[pd.DataFrame]:
    frames = []
    with requests.Session() as session:
        for metric_name, (path, source_column) in BGEOMETRICS_METRICS.items():
            try:
                if metric_name == "hashribbons":
                    params = {"startday": start_date, "endday": end_date}
                    token = os.getenv(BGEOMETRICS_TOKEN_ENV)
                    if token:
                        params["token"] = token
                    raw = _request_json(session, f"{BGEOMETRICS_BASE_URL}{path}", params=params)
                    raw_frame = pd.DataFrame(_extract_records(raw))
                    frame = pd.DataFrame(columns=["date", "hashrate_sma_30", "hashrate_sma_60", "hashribbon_trend"])
                    if not raw_frame.empty and "d" in raw_frame.columns:
                        frame = pd.DataFrame(
                            {
                                "date": raw_frame["d"].astype(str),
                                "hashrate_sma_30": pd.to_numeric(
                                    raw_frame["sma_30"] if "sma_30" in raw_frame else np.nan,
                                    errors="coerce",
                                ),
                                "hashrate_sma_60": pd.to_numeric(
                                    raw_frame["sma_60"] if "sma_60" in raw_frame else np.nan,
                                    errors="coerce",
                                ),
                            }
                        )
                    if not raw_frame.empty and "d" in raw_frame.columns and source_column in raw_frame:
                        trend_frame = pd.DataFrame(
                            {
                                "date": raw_frame["d"].astype(str),
                                "hashribbon_trend": raw_frame[source_column].astype(str),
                            }
                        )
                        frame = frame.merge(trend_frame, on="date", how="left")
                else:
                    frame = _fetch_bgeometrics_series(
                        session,
                        path,
                        {metric_name: source_column},
                        start_date,
                        end_date,
                    )
                if not frame.empty:
                    frames.append(frame)
            except Exception as exc:  # pragma: no cover - network best effort
                print(f"[cycle_metrics] {metric_name} unavailable: {exc}")
    return frames


def _load_existing_cycle_snapshot(start_date: str, end_date: str) -> pd.DataFrame:
    columns = ", ".join(["date", *PRESERVED_REMOTE_COLUMNS])
    query = (
        f"SELECT {columns} FROM btc_cycle_metrics WHERE date >= ? AND date <= ? ORDER BY date"
    )
    try:
        conn = duckdb.connect(DB_PATH)
    except duckdb.Error:
        return pd.DataFrame(columns=["date", *PRESERVED_REMOTE_COLUMNS])
    try:
        df = pd.read_sql_query(query, conn, params=[start_date, end_date])
    except Exception:
        return pd.DataFrame(columns=["date", *PRESERVED_REMOTE_COLUMNS])
    finally:
        conn.close()
    return df


def _compute_pi_cycle_frame(dates: pd.Series, close: pd.Series) -> pd.DataFrame:
    price = pd.to_numeric(close, errors="coerce")
    pi_sma111 = price.rolling(111, min_periods=111).mean()
    pi_sma350x2 = price.rolling(350, min_periods=350).mean() * 2.0

    current_above = pi_sma111 > pi_sma350x2
    previous_above = current_above.shift(1)
    pi_signal = pd.Series(
        np.select(
            [
                current_above & previous_above.eq(False),
                (~current_above) & previous_above.eq(True),
            ],
            [1, -1],
            default=0,
        ),
        index=dates.index,
        dtype="int64",
    )

    return pd.DataFrame(
        {
            "date": dates.astype(str),
            "pi_sma111": pi_sma111.to_numpy(),
            "pi_sma350x2": pi_sma350x2.to_numpy(),
            "pi_cycle_signal": pi_signal.to_numpy(),
        }
    )


def _adaptive_top_threshold(
    series: pd.Series,
    *,
    quantile: float,
    floor: float,
    ceiling: float,
    default: float,
) -> pd.Series:
    threshold = series.shift(1).rolling(CYCLE_WINDOW_DAYS, min_periods=CYCLE_MIN_PERIODS).quantile(quantile)
    threshold = threshold.clip(lower=floor, upper=ceiling)
    return threshold.ffill().fillna(default)


def _adaptive_low_extreme(
    series: pd.Series,
    *,
    quantile: float,
    floor: float,
    ceiling: float,
    default: float,
) -> pd.Series:
    threshold = series.shift(1).rolling(CYCLE_WINDOW_DAYS, min_periods=CYCLE_MIN_PERIODS).quantile(quantile)
    threshold = threshold.clip(lower=floor, upper=ceiling)
    return threshold.ffill().fillna(default)


def _strength_high(value, start, full) -> float | None:
    if pd.isna(value) or pd.isna(start) or pd.isna(full):
        return None
    if full <= start:
        return float(value >= full)
    if value <= start:
        return 0.0
    if value >= full:
        return 1.0
    return float((value - start) / (full - start))


def _strength_low(value, start, full) -> float | None:
    if pd.isna(value) or pd.isna(start) or pd.isna(full):
        return None
    if full >= start:
        return float(value <= full)
    if value >= start:
        return 0.0
    if value <= full:
        return 1.0
    return float((start - value) / (start - full))


def _decay_scores(events: pd.Series, horizon_days: int) -> pd.Series:
    scores: list[float] = []
    last_event_index: int | None = None

    for idx, event in enumerate(events.fillna(False).astype(bool)):
        if event:
            last_event_index = idx
            scores.append(1.0)
            continue

        if last_event_index is None:
            scores.append(0.0)
            continue

        age = idx - last_event_index
        scores.append(max(0.0, 1.0 - age / horizon_days))

    return pd.Series(scores, index=events.index, dtype="float64")


def _weighted_score(frame: pd.DataFrame, columns: list[tuple[str, float]]) -> pd.Series:
    weights = pd.DataFrame(
        {column: np.where(frame[column].notna(), weight, 0.0) for column, weight in columns},
        index=frame.index,
    )
    weighted_values = pd.DataFrame(
        {column: frame[column].fillna(0.0) * weight for column, weight in columns},
        index=frame.index,
    )
    total_weight = weights.sum(axis=1)
    total_value = weighted_values.sum(axis=1)
    return (total_value / total_weight.replace(0, np.nan)).fillna(0.0)


def _cycle_zone(top_score: float, bottom_score: float) -> str:
    if top_score >= 0.7 and top_score >= bottom_score + 0.15:
        return "top_zone"
    if bottom_score >= 0.7 and bottom_score >= top_score + 0.15:
        return "bottom_zone"
    if top_score >= 0.45 and top_score > bottom_score:
        return "top_watch"
    if bottom_score >= 0.45 and bottom_score > top_score:
        return "bottom_watch"
    if top_score >= 0.35 and bottom_score >= 0.35:
        return "mixed"
    return "neutral"


def _compute_cycle_scores(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()

    frame["mvrv_top_threshold"] = _adaptive_top_threshold(
        frame["mvrv_zscore"],
        quantile=0.90,
        floor=4.5,
        ceiling=8.0,
        default=6.0,
    )
    frame["nupl_top_threshold"] = _adaptive_top_threshold(
        frame["nupl"],
        quantile=0.90,
        floor=0.60,
        ceiling=0.78,
        default=0.70,
    )
    frame["puell_top_threshold"] = _adaptive_top_threshold(
        frame["puell_multiple"],
        quantile=0.90,
        floor=2.2,
        ceiling=5.0,
        default=3.5,
    )

    frame["mvrv_bottom_extreme"] = _adaptive_low_extreme(
        frame["mvrv_zscore"],
        quantile=0.10,
        floor=-1.20,
        ceiling=-0.25,
        default=-0.40,
    )
    frame["nupl_bottom_extreme"] = _adaptive_low_extreme(
        frame["nupl"],
        quantile=0.10,
        floor=-0.35,
        ceiling=-0.05,
        default=-0.10,
    )
    frame["puell_bottom_extreme"] = _adaptive_low_extreme(
        frame["puell_multiple"],
        quantile=0.15,
        floor=0.15,
        ceiling=0.40,
        default=0.30,
    )

    frame["hashribbon_buy_signal"] = (
        (frame["hashrate_sma_30"] > frame["hashrate_sma_60"])
        & (frame["hashrate_sma_30"].shift(1) <= frame["hashrate_sma_60"].shift(1))
    ).astype("int64")
    frame["hashribbon_sell_signal"] = (
        (frame["hashrate_sma_30"] < frame["hashrate_sma_60"])
        & (frame["hashrate_sma_30"].shift(1) >= frame["hashrate_sma_60"].shift(1))
    ).astype("int64")

    frame["mvrv_top_score"] = [
        _strength_high(value, threshold * 0.90, threshold * 1.15)
        for value, threshold in zip(frame["mvrv_zscore"], frame["mvrv_top_threshold"])
    ]
    frame["nupl_top_score"] = [
        _strength_high(value, max(threshold * 0.90, 0.55), min(threshold * 1.10, 0.92))
        for value, threshold in zip(frame["nupl"], frame["nupl_top_threshold"])
    ]
    frame["puell_top_score"] = [
        _strength_high(value, threshold * 0.90, threshold * 1.20)
        for value, threshold in zip(frame["puell_multiple"], frame["puell_top_threshold"])
    ]

    frame["mvrv_bottom_score"] = [
        _strength_low(value, 0.0, extreme)
        for value, extreme in zip(frame["mvrv_zscore"], frame["mvrv_bottom_extreme"])
    ]
    frame["nupl_bottom_score"] = [
        _strength_low(value, 0.0, extreme)
        for value, extreme in zip(frame["nupl"], frame["nupl_bottom_extreme"])
    ]
    frame["puell_bottom_score"] = [
        _strength_low(value, 0.50, extreme)
        for value, extreme in zip(frame["puell_multiple"], frame["puell_bottom_extreme"])
    ]

    frame["pi_cycle_top_score"] = _decay_scores(frame["pi_cycle_signal"] == 1, 30)
    frame["pi_cycle_bottom_score"] = _decay_scores(frame["pi_cycle_signal"] == -1, 30)
    frame["hashribbon_bottom_score"] = _decay_scores(frame["hashribbon_buy_signal"] == 1, 45)

    frame["top_score"] = _weighted_score(
        frame,
        [
            ("mvrv_top_score", 0.35),
            ("nupl_top_score", 0.30),
            ("puell_top_score", 0.15),
            ("pi_cycle_top_score", 0.20),
        ],
    )
    frame["bottom_score"] = _weighted_score(
        frame,
        [
            ("mvrv_bottom_score", 0.35),
            ("nupl_bottom_score", 0.25),
            ("puell_bottom_score", 0.20),
            ("hashribbon_bottom_score", 0.20),
        ],
    )
    frame["cycle_bias"] = frame["top_score"] - frame["bottom_score"]
    frame["cycle_zone"] = [
        _cycle_zone(float(top_score), float(bottom_score))
        for top_score, bottom_score in zip(frame["top_score"], frame["bottom_score"])
    ]

    return frame


def init_cycle_metrics_table(conn: duckdb.DuckDBPyConnection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS btc_cycle_metrics (
            date TEXT PRIMARY KEY
        )
        """
    )
    existing_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(btc_cycle_metrics)").fetchall()
    }
    for column, column_type in CYCLE_METRIC_COLUMNS.items():
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE btc_cycle_metrics ADD COLUMN {column} {column_type}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cycle_metrics_zone ON btc_cycle_metrics(cycle_zone)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cycle_metrics_version ON btc_cycle_metrics(source_version)"
    )
    conn.commit()


def build_cycle_metrics(df_ohlcv: pd.DataFrame) -> pd.DataFrame:
    df = _normalize_ohlcv(df_ohlcv)
    close = pd.to_numeric(df["close"], errors="coerce")

    features = pd.DataFrame(
        {
            "date": pd.to_datetime(df.index).strftime("%Y-%m-%d"),
            "price": close.to_numpy(),
        }
    ).reset_index(drop=True)
    start_date = features["date"].iloc[0]
    end_date = features["date"].iloc[-1]

    remote_base = features[["date"]].copy()
    for frame in _fetch_remote_cycle_frames(start_date, end_date):
        remote_base = remote_base.merge(frame.reset_index(drop=True), on="date", how="left")

    existing_snapshot = _load_existing_cycle_snapshot(start_date, end_date)
    if not existing_snapshot.empty:
        remote_base = remote_base.merge(existing_snapshot, on="date", how="left", suffixes=("", "_stored"))
        for column in PRESERVED_REMOTE_COLUMNS:
            stored_column = f"{column}_stored"
            if stored_column in remote_base.columns:
                remote_base[column] = remote_base[column].combine_first(remote_base[stored_column])
                remote_base = remote_base.drop(columns=[stored_column])

    for column in PRESERVED_REMOTE_COLUMNS:
        if column not in remote_base.columns:
            remote_base[column] = np.nan

    numeric_ffill_columns = [
        "mvrv_zscore",
        "nupl",
        "puell_multiple",
        "hashrate_sma_30",
        "hashrate_sma_60",
    ]
    remote_base[numeric_ffill_columns] = remote_base[numeric_ffill_columns].ffill()
    remote_base["hashribbon_trend"] = remote_base["hashribbon_trend"].ffill()

    pi_frame = _compute_pi_cycle_frame(features["date"], close.reset_index(drop=True))
    features = features.merge(remote_base, on="date", how="left")
    features = features.merge(pi_frame, on="date", how="left")
    features = _compute_cycle_scores(features)
    features["source_version"] = CYCLE_SOURCE_VERSION

    for column in CYCLE_METRIC_COLUMNS:
        if column not in features.columns:
            features[column] = np.nan

    return features[list(CYCLE_METRIC_COLUMNS.keys())].replace({np.nan: None})


def save_cycle_metrics_to_db(conn: duckdb.DuckDBPyConnection, cycle_df: pd.DataFrame):
    if cycle_df.empty:
        return

    init_cycle_metrics_table(conn)
    columns = list(CYCLE_METRIC_COLUMNS.keys())
    records = [tuple(row[column] for column in columns) for _, row in cycle_df.iterrows()]
    placeholders = ", ".join(["?"] * len(columns))
    column_sql = ", ".join(columns)
    conn.executemany(
        f"""
        INSERT INTO btc_cycle_metrics ({column_sql})
        VALUES ({placeholders})
        ON CONFLICT (date) DO UPDATE SET
        {", ".join(f"{column}=EXCLUDED.{column}" for column in columns if column != "date")}
        """,
        records,
    )
    conn.commit()
