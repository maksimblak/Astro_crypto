"""
BTC Research: Пики и Дно 2016-2026
Zigzag-алгоритм для поиска разворотов с порогами 10% (локальные) и 20% (крупные).
Данные сохраняются в DuckDB (btc_research.duckdb) и CSV.
"""

import os
import duckdb
import yfinance as yf
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from astro_shared import yfinance_exclusive_end
from derivatives_history import save_derivatives_history_to_db
from log import get_logger
from market_features import build_market_features, save_market_features_to_db

logger = get_logger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "btc_research.duckdb")


def init_db():
    """Создаёт таблицы в DuckDB."""
    conn = duckdb.connect(DB_PATH)
    c = conn.cursor()

    # Таблица дневных цен
    c.execute("""
        CREATE TABLE IF NOT EXISTS btc_daily (
            date TEXT PRIMARY KEY,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL
        )
    """)

    # Таблица пиков и дно
    c.execute("""
        CREATE TABLE IF NOT EXISTS btc_pivots (
            id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            price REAL NOT NULL,
            type TEXT NOT NULL,
            pct_change REAL,
            UNIQUE(date, type)
        )
    """)

    # Индексы для быстрых запросов
    c.execute("CREATE INDEX IF NOT EXISTS idx_pivots_type ON btc_pivots(type)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pivots_date ON btc_pivots(date)")

    conn.commit()
    return conn


def download_btc_data(start: str = "2016-01-01", end: str | None = None) -> pd.DataFrame:
    """Загружает daily OHLCV BTC/USD через yfinance."""
    end = end or yfinance_exclusive_end()
    logger.info(f"Загрузка BTC-USD данных за {start} — {end}...")
    df = yf.download("BTC-USD", start=start, end=end, progress=False)
    df.index = df.index.tz_localize(None)
    # yfinance может вернуть MultiIndex колонки — убираем
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    logger.info(f"Загружено {len(df)} дней данных.")
    return df


def save_daily_to_db(conn: duckdb.DuckDBPyConnection, df: pd.DataFrame):
    """Сохраняет дневные цены в DuckDB."""
    records = []
    for date, row in df.iterrows():
        records.append((
            date.strftime("%Y-%m-%d"),
            round(float(row["Open"]), 2),
            round(float(row["High"]), 2),
            round(float(row["Low"]), 2),
            round(float(row["Close"]), 2),
            round(float(row["Volume"]), 0),
        ))
    conn.executemany(
        "INSERT OR REPLACE INTO btc_daily (date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?)",
        records
    )
    conn.commit()
    logger.info(f"Сохранено {len(records)} дневных свечей в БД.")


def load_existing_daily_from_db(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Возвращает уже сохранённый OHLCV snapshot из btc_daily в формате yfinance."""
    df = pd.read_sql_query(
        "SELECT date, open, high, low, close, volume FROM btc_daily ORDER BY date",
        conn,
        parse_dates=["date"],
    )
    if df.empty:
        return pd.DataFrame()
    df = df.set_index("date")
    return df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )


def zigzag(prices: pd.Series, threshold) -> list[dict]:
    """
    Zigzag-алгоритм: находит развороты где цена отклонилась
    от последнего экстремума на >= threshold.

    threshold может быть:
    - float: фиксированный порог (0.1 = 10%)
    - callable: функция (price) -> float, адаптивный порог
    """
    if len(prices) < 2:
        return []

    def get_threshold(price):
        if callable(threshold):
            return threshold(price)
        return threshold

    points = []
    current_high_idx = prices.index[0]
    current_high = prices.iloc[0]
    current_low_idx = prices.index[0]
    current_low = prices.iloc[0]
    direction = 0

    for i in range(1, len(prices)):
        date = prices.index[i]
        price = prices.iloc[i]
        th = get_threshold(price)

        if direction == 0:
            if price >= current_low * (1 + th):
                points.append({"date": current_low_idx, "price": current_low, "type": "low"})
                current_high = price
                current_high_idx = date
                direction = 1
            elif price <= current_high * (1 - th):
                points.append({"date": current_high_idx, "price": current_high, "type": "high"})
                current_low = price
                current_low_idx = date
                direction = -1
            else:
                if price > current_high:
                    current_high = price
                    current_high_idx = date
                if price < current_low:
                    current_low = price
                    current_low_idx = date

        elif direction == 1:
            if price > current_high:
                current_high = price
                current_high_idx = date
            elif price <= current_high * (1 - th):
                points.append({"date": current_high_idx, "price": current_high, "type": "high"})
                current_low = price
                current_low_idx = date
                direction = -1

        elif direction == -1:
            if price < current_low:
                current_low = price
                current_low_idx = date
            elif price >= current_low * (1 + th):
                points.append({"date": current_low_idx, "price": current_low, "type": "low"})
                current_high = price
                current_high_idx = date
                direction = 1

    if direction == 1:
        points.append({"date": current_high_idx, "price": current_high, "type": "high"})
    elif direction == -1:
        points.append({"date": current_low_idx, "price": current_low, "type": "low"})

    return points


def adaptive_micro_threshold(price: float) -> float:
    """
    Адаптивный порог для micro разворотов:
    - BTC < $5K   → 10% (не дублирует local)
    - BTC $5-20K  → 8%
    - BTC $20-50K → 7%
    - BTC > $50K  → 5%
    """
    if price < 5_000:
        return 0.10
    elif price < 20_000:
        return 0.08
    elif price < 50_000:
        return 0.07
    else:
        return 0.05


def classify_points(
    prices: pd.Series,
    major_threshold: float = 0.20,
    local_threshold: float = 0.10,
) -> pd.DataFrame:
    """
    Находит и классифицирует все пики/дно по 2 уровням:
    - global: ATH / ATL
    - major: развороты > 20%
    - local: развороты > 10%
    """
    major_points = zigzag(prices, major_threshold)
    local_points = zigzag(prices, local_threshold)

    global_high_idx = prices.idxmax()
    global_low_idx = prices.idxmin()
    major_dates = {p["date"] for p in major_points}

    results = []

    # Major + global
    for p in major_points:
        ptype = p["type"]
        if p["date"] == global_high_idx:
            label = "global_high"
        elif p["date"] == global_low_idx:
            label = "global_low"
        else:
            label = f"major_{ptype}"
        results.append({"date": p["date"], "price": round(p["price"], 2), "type": label})

    # Local (не пересекается с major)
    for p in local_points:
        if p["date"] not in major_dates:
            results.append({"date": p["date"], "price": round(p["price"], 2), "type": f"local_{p['type']}"})

    # Гарантируем наличие глобальных экстремумов
    result_dates = {r["date"] for r in results}
    if global_high_idx not in result_dates:
        results.append({"date": global_high_idx, "price": round(prices[global_high_idx], 2), "type": "global_high"})
    if global_low_idx not in result_dates:
        results.append({"date": global_low_idx, "price": round(prices[global_low_idx], 2), "type": "global_low"})

    df = pd.DataFrame(results).sort_values("date").reset_index(drop=True)
    df["pct_change"] = df["price"].pct_change().mul(100).round(2)

    return df


def save_pivots_to_db(conn: duckdb.DuckDBPyConnection, df: pd.DataFrame):
    """Сохраняет пики/дно в DuckDB."""
    conn.execute("DELETE FROM btc_pivots")
    records = []
    for _, row in df.iterrows():
        date_str = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])
        records.append((date_str, row["price"], row["type"], row["pct_change"] if pd.notna(row["pct_change"]) else None))
    conn.executemany(
        "INSERT INTO btc_pivots (date, price, type, pct_change) VALUES (?, ?, ?, ?)",
        records
    )
    conn.commit()
    logger.info(f"Сохранено {len(records)} точек разворота в БД.")


def print_results(df: pd.DataFrame):
    """Выводит результаты в консоль."""
    type_labels = {
        "global_high": "ATH (глобальный пик)",
        "global_low":  "ATL (глобальное дно)",
        "major_high":  "Крупный пик (>20%)",
        "major_low":   "Крупное дно (>20%)",
        "local_high":  "Локальный пик (>10%)",
        "local_low":   "Локальное дно (>10%)",
    }

    print("\n" + "=" * 85)
    print("BTC ПИКИ И ДНО — 2016-2026")
    print("=" * 85)

    major = df[df["type"].str.contains("global|major")]
    local = df[df["type"].str.contains("local")]

    def _print_section(subset, title):
        print(f"\n--- {title} ---")
        for _, row in subset.iterrows():
            label = type_labels.get(row["type"], row["type"])
            date_str = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])
            pct = f" ({row['pct_change']:+.1f}%)" if pd.notna(row["pct_change"]) else ""
            print(f"  {date_str}  ${row['price']:>10,.2f}  {label}{pct}")

    _print_section(major, "КРУПНЫЕ РАЗВОРОТЫ (>20%) + ГЛОБАЛЬНЫЕ")
    _print_section(local, "ЛОКАЛЬНЫЕ РАЗВОРОТЫ (>10%)")
    print(f"\nВсего: {len(df)} точек (major/global: {len(major)}, local: {len(local)})")


def print_db_examples(conn: duckdb.DuckDBPyConnection):
    """Показывает примеры SQL-запросов к базе."""
    print("\n" + "=" * 85)
    print("ПРИМЕРЫ SQL-ЗАПРОСОВ К btc_research.duckdb")
    print("=" * 85)

    queries = [
        ("Все ATH и ATL:", "SELECT * FROM btc_pivots WHERE type LIKE 'global_%' ORDER BY date"),
        ("Крупные дно (>20%):", "SELECT date, price, pct_change FROM btc_pivots WHERE type = 'major_low' ORDER BY date"),
        ("Топ-5 самых глубоких падений:", "SELECT date, price, pct_change FROM btc_pivots WHERE pct_change < 0 ORDER BY pct_change ASC LIMIT 5"),
        ("Количество разворотов по годам:", "SELECT substr(date, 1, 4) as year, type, COUNT(*) as cnt FROM btc_pivots GROUP BY year, type ORDER BY year, type"),
    ]

    for title, sql in queries:
        print(f"\n  {title}")
        print(f"  SQL: {sql}")
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        print(f"  {'  |  '.join(cols)}")
        print(f"  {'-' * 60}")
        for row in rows:
            print(f"  {'  |  '.join(str(v) for v in row)}")


def plot_chart(prices: pd.Series, df: pd.DataFrame, save_path: str = os.path.join(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "charts"), "btc_chart.png")):
    """Строит график BTC с отмеченными пиками и дно."""
    fig, ax = plt.subplots(figsize=(24, 12))

    ax.plot(prices.index, prices.values, color="#555555", linewidth=0.8, alpha=0.8)

    style_map = {
        "global_high": {"color": "red", "marker": "v", "size": 250, "label": "ATH"},
        "global_low":  {"color": "green", "marker": "^", "size": 250, "label": "ATL"},
        "major_high":  {"color": "red", "marker": "v", "size": 140, "label": "Major High (>20%)"},
        "major_low":   {"color": "green", "marker": "^", "size": 140, "label": "Major Low (>20%)"},
        "local_high":  {"color": "orange", "marker": "v", "size": 70, "label": "Local High (>10%)"},
        "local_low":   {"color": "#90EE90", "marker": "^", "size": 70, "label": "Local Low (>10%)"},
    }

    plotted_labels = set()
    for _, row in df.iterrows():
        style = style_map.get(row["type"], {"color": "gray", "marker": "o", "size": 30, "label": row["type"]})
        label = style["label"] if style["label"] not in plotted_labels else None
        plotted_labels.add(style["label"])

        ax.scatter(row["date"], row["price"], color=style["color"], marker=style["marker"],
                   s=style["size"], zorder=5, label=label, edgecolors="black", linewidths=0.3)

        # Подписи только для major и global (micro/local слишком мелкие)
        if "global" in row["type"] or "major" in row["type"]:
            offset = 18 if "high" in row["type"] else -18
            ax.annotate(
                f"${row['price']:,.0f}\n{row['date'].strftime('%d.%m.%y')}",
                (row["date"], row["price"]),
                textcoords="offset points", xytext=(0, offset),
                fontsize=5.5, ha="center", alpha=0.85,
            )

    ax.set_title("BTC/USD — Пики и Дно 2016-2026 (major >20%, local >10%)", fontsize=16, fontweight="bold")
    ax.set_ylabel("Цена (USD)", fontsize=12)
    ax.set_xlabel("Дата", fontsize=12)
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.xticks(rotation=45)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    logger.info(f"График сохранён: {save_path}")
    plt.close()


def main():
    # 1. Инициализация БД
    conn = init_db()

    # 2. Загрузка данных
    df_ohlcv = download_btc_data("2016-01-01")
    if df_ohlcv.empty:
        logger.warning("yfinance вернул пустой набор. Использую текущий snapshot из btc_daily.")
        df_ohlcv = load_existing_daily_from_db(conn)
        if df_ohlcv.empty:
            conn.close()
            raise RuntimeError("Нет свежих данных из yfinance и btc_daily тоже пустая.")

    prices = df_ohlcv["Close"].squeeze()

    # 3. Сохраняем дневные цены в БД
    if not df_ohlcv.empty and "Open" in df_ohlcv.columns:
        save_daily_to_db(conn, df_ohlcv)

    # 3b. Строим market-features для режима рынка
    market_features_df, derivatives_history_df = build_market_features(df_ohlcv)
    save_market_features_to_db(conn, market_features_df)
    save_derivatives_history_to_db(conn, derivatives_history_df)

    # 4. Поиск и классификация пиков/дно
    df = classify_points(prices, major_threshold=0.20, local_threshold=0.10)

    # 5. Сохраняем в БД и CSV
    save_pivots_to_db(conn, df)

    csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "btc_peaks_valleys.csv")
    df_csv = df.copy()
    df_csv["date"] = df_csv["date"].dt.strftime("%Y-%m-%d")
    df_csv.to_csv(csv_path, index=False)
    logger.info(f"CSV сохранён: {csv_path}")

    # 6. Вывод в консоль
    print_results(df)

    # 7. График
    plot_chart(prices, df, os.path.join(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "charts"), "btc_chart.png"))

    # 8. Примеры запросов к БД
    print_db_examples(conn)

    conn.close()
    logger.info(f"БД сохранена: {DB_PATH}")
    print("Подключение: duckdb btc_research.duckdb")


if __name__ == "__main__":
    main()
