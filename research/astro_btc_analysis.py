"""
BTC x Астрология: Корреляционный анализ BTC
Проверяем влияние астрологических факторов на цену биткоина.

Факторы:
1. Фазы Луны (новолуние, полнолуние, растущая, убывающая)
2. Ретроградный Меркурий
3. Затмения (солнечные, лунные)
4. Луна в знаках зодиака
5. Аспекты планет (Юпитер-Сатурн, Марс-Юпитер и др.)
"""

import duckdb
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from astro_shared import (
    DB_PATH, ZODIAC_SIGNS, get_zodiac_sign,
    planet_lon_deg,
    moon_phase_percent,
    previous_new_moon, next_new_moon,
    previous_full_moon, next_full_moon,
)

# ============================================================
# 1. ЗАГРУЗКА ДАННЫХ BTC
# ============================================================

def load_btc_data() -> pd.DataFrame:
    conn = duckdb.connect(DB_PATH)
    df = pd.read_sql("""
        SELECT date, open, high, low, close, volume
        FROM btc_daily
        ORDER BY date
    """, conn)
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    df["return_pct"] = df["close"].pct_change() * 100
    df["return_5d"] = df["close"].pct_change(5) * 100
    df["return_7d"] = df["close"].pct_change(7) * 100
    df["volatility"] = df["return_pct"].rolling(7).std()
    return df


# ============================================================
# 2. АСТРОЛОГИЧЕСКИЕ РАСЧЁТЫ
# ============================================================

def compute_moon_phase(date) -> dict:
    """Вычисляет фазу Луны на дату."""
    d = date

    # Фаза: 0 = новолуние, 0.5 = полнолуние
    phase = moon_phase_percent(d) / 100.0

    # Ближайшие фазы
    prev_new = previous_new_moon(d)
    next_new = next_new_moon(d)
    next_full = next_full_moon(d)

    # Определяем четверть
    cycle_length = (next_new - prev_new).total_seconds()
    position = (d - prev_new).total_seconds() / cycle_length if cycle_length else 0

    if position < 0.125 or position >= 0.875:
        quarter = "new_moon"
    elif 0.125 <= position < 0.375:
        quarter = "waxing"  # растущая
    elif 0.375 <= position < 0.625:
        quarter = "full_moon"
    else:
        quarter = "waning"  # убывающая

    # Знак Луны (эклиптическая долгота)
    moon_lon = planet_lon_deg("Луна", d)
    moon_sign = get_zodiac_sign(moon_lon)

    days_to_new = (next_new - d).total_seconds() / 86400.0
    days_to_full = (next_full - d).total_seconds() / 86400.0

    return {
        "moon_phase": round(phase, 4),
        "moon_quarter": quarter,
        "moon_sign": moon_sign,
        "days_to_new": round(days_to_new, 2),
        "days_to_full": round(days_to_full, 2),
    }


def is_mercury_retrograde(date) -> bool:
    """Определяет ретроградность Меркурия."""
    from astro_shared import is_retrograde
    d_prev = date - timedelta(days=1)
    return is_retrograde("Меркурий", date, d_prev)


def get_planet_positions(date) -> dict:
    """Получает позиции основных планет."""
    planet_map = {
        "mars": "Марс",
        "jupiter": "Юпитер",
        "saturn": "Сатурн",
        "venus": "Венера",
    }

    positions = {}
    for eng_name, ru_name in planet_map.items():
        lon = planet_lon_deg(ru_name, date)
        positions[f"{eng_name}_sign"] = get_zodiac_sign(lon)
        positions[f"{eng_name}_lon"] = round(lon, 2)

    return positions


def compute_aspects(date) -> list[str]:
    """Находит значимые аспекты между планетами."""
    planet_names = ["Mars", "Jupiter", "Saturn", "Venus", "Mercury"]
    ru_names = {"Mars": "Марс", "Jupiter": "Юпитер", "Saturn": "Сатурн",
                "Venus": "Венера", "Mercury": "Меркурий"}

    lons = {}
    for name in planet_names:
        lons[name] = planet_lon_deg(ru_names[name], date)

    # Аспекты: соединение (0°), секстиль (60°), квадратура (90°), трин (120°), оппозиция (180°)
    aspect_types = {
        "conjunction": (0, 8),    # орбис ±8°
        "sextile": (60, 6),
        "square": (90, 8),
        "trine": (120, 8),
        "opposition": (180, 8),
    }

    aspects = []
    planet_names = list(lons.keys())
    for i in range(len(planet_names)):
        for j in range(i + 1, len(planet_names)):
            p1, p2 = planet_names[i], planet_names[j]
            diff = abs(lons[p1] - lons[p2])
            if diff > 180:
                diff = 360 - diff

            for aspect_name, (angle, orb) in aspect_types.items():
                if abs(diff - angle) <= orb:
                    aspects.append(f"{p1}-{p2}_{aspect_name}")

    return aspects


# Затмения 2020-2026 (известные даты)
ECLIPSES = [
    # (дата, тип)
    ("2020-01-10", "lunar"),
    ("2020-06-05", "lunar"),
    ("2020-06-21", "solar"),
    ("2020-07-05", "lunar"),
    ("2020-11-30", "lunar"),
    ("2020-12-14", "solar"),
    ("2021-05-26", "lunar"),
    ("2021-06-10", "solar"),
    ("2021-11-19", "lunar"),
    ("2021-12-04", "solar"),
    ("2022-04-30", "solar"),
    ("2022-05-16", "lunar"),
    ("2022-10-25", "solar"),
    ("2022-11-08", "lunar"),
    ("2023-04-20", "solar"),
    ("2023-05-05", "lunar"),
    ("2023-10-14", "solar"),
    ("2023-10-28", "lunar"),
    ("2024-03-25", "lunar"),
    ("2024-04-08", "solar"),
    ("2024-09-18", "lunar"),
    ("2024-10-02", "solar"),
    ("2025-03-14", "lunar"),
    ("2025-03-29", "solar"),
    ("2025-09-07", "lunar"),
    ("2025-09-21", "solar"),
    ("2026-02-17", "solar"),
    ("2026-03-03", "lunar"),
]


# Затмения 2020-2026 (известные даты)
ECLIPSES = [
    # (дата, тип)
    ("2020-01-10", "lunar"),
    ("2020-06-05", "lunar"),
    ("2020-06-21", "solar"),
    ("2020-07-05", "lunar"),
    ("2020-11-30", "lunar"),
    ("2020-12-14", "solar"),
    ("2021-05-26", "lunar"),
    ("2021-06-10", "solar"),
    ("2021-11-19", "lunar"),
    ("2021-12-04", "solar"),
    ("2022-04-30", "solar"),
    ("2022-05-16", "lunar"),
    ("2022-10-25", "solar"),
    ("2022-11-08", "lunar"),
    ("2023-04-20", "solar"),
    ("2023-05-05", "lunar"),
    ("2023-10-14", "solar"),
    ("2023-10-28", "lunar"),
    ("2024-03-25", "lunar"),
    ("2024-04-08", "solar"),
    ("2024-09-18", "lunar"),
    ("2024-10-02", "solar"),
    ("2025-03-14", "lunar"),
    ("2025-03-29", "solar"),
    ("2025-09-07", "lunar"),
    ("2025-09-21", "solar"),
    ("2026-02-17", "solar"),
    ("2026-03-03", "lunar"),
]


# ============================================================
# 3. СБОРКА ДАННЫХ
# ============================================================

def build_astro_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Добавляет астрологические колонки к BTC данным."""
    print("Вычисление астрологических данных...")

    moon_data = []
    mercury_retro = []
    eclipse_proximity = []
    aspects_data = []

    eclipse_dates = [datetime.strptime(e[0], "%Y-%m-%d") for e in ECLIPSES]

    for i, row in df.iterrows():
        date = row["date"].to_pydatetime()

        # Луна
        moon = compute_moon_phase(date)
        moon_data.append(moon)

        # Меркурий
        mercury_retro.append(is_mercury_retrograde(date))

        # Близость к затмению (±10 дней)
        min_days = min(abs((date - ed).days) for ed in eclipse_dates)
        eclipse_proximity.append(min_days)

        # Аспекты
        aspects = compute_aspects(date)
        aspects_data.append(aspects)

        if (i + 1) % 200 == 0:
            print(f"  Обработано {i + 1}/{len(df)} дней...")

    # Добавляем колонки
    moon_df = pd.DataFrame(moon_data)
    df = pd.concat([df.reset_index(drop=True), moon_df], axis=1)
    df["mercury_retro"] = mercury_retro
    df["eclipse_days"] = eclipse_proximity
    df["eclipse_window"] = df["eclipse_days"] <= 7
    df["n_aspects"] = [len(a) for a in aspects_data]
    df["has_square"] = [any("square" in x for x in a) for a in aspects_data]
    df["has_conjunction"] = [any("conjunction" in x for x in a) for a in aspects_data]
    df["has_opposition"] = [any("opposition" in x for x in a) for a in aspects_data]
    df["has_trine"] = [any("trine" in x for x in a) for a in aspects_data]

    print(f"  Готово: {len(df)} дней с астро-данными.")
    return df


# ============================================================
# 4. СТАТИСТИЧЕСКИЙ АНАЛИЗ
# ============================================================

def analyze_moon_phases(df: pd.DataFrame) -> dict:
    """Анализ доходности по фазам Луны."""
    results = {}

    for quarter in ["new_moon", "waxing", "full_moon", "waning"]:
        mask = df["moon_quarter"] == quarter
        returns = df.loc[mask, "return_pct"].dropna()
        rest = df.loc[~mask, "return_pct"].dropna()

        t_stat, p_value = stats.ttest_ind(returns, rest)

        results[quarter] = {
            "count": len(returns),
            "mean_return": round(returns.mean(), 4),
            "median_return": round(returns.median(), 4),
            "std": round(returns.std(), 4),
            "volatility": round(returns.std(), 4),
            "positive_pct": round((returns > 0).mean() * 100, 1),
            "t_stat": round(t_stat, 3),
            "p_value": round(p_value, 4),
            "significant": p_value < 0.05,
        }

    return results


def analyze_moon_signs(df: pd.DataFrame) -> pd.DataFrame:
    """Анализ доходности по знакам Луны."""
    results = []
    overall_mean = df["return_pct"].dropna().mean()

    for sign in ZODIAC_SIGNS:
        mask = df["moon_sign"] == sign
        returns = df.loc[mask, "return_pct"].dropna()
        rest = df.loc[~mask, "return_pct"].dropna()

        if len(returns) < 10:
            continue

        t_stat, p_value = stats.ttest_ind(returns, rest)

        results.append({
            "sign": sign,
            "count": len(returns),
            "mean_return": round(returns.mean(), 4),
            "median_return": round(returns.median(), 4),
            "positive_pct": round((returns > 0).mean() * 100, 1),
            "vs_average": round(returns.mean() - overall_mean, 4),
            "t_stat": round(t_stat, 3),
            "p_value": round(p_value, 4),
        })

    return pd.DataFrame(results).sort_values("mean_return", ascending=False)


def analyze_mercury_retrograde(df: pd.DataFrame) -> dict:
    """Анализ доходности в периоды ретроградного Меркурия."""
    retro = df[df["mercury_retro"]]["return_pct"].dropna()
    direct = df[~df["mercury_retro"]]["return_pct"].dropna()

    t_stat, p_value = stats.ttest_ind(retro, direct)

    # 7-дневная доходность
    retro_7d = df[df["mercury_retro"]]["return_7d"].dropna()
    direct_7d = df[~df["mercury_retro"]]["return_7d"].dropna()
    t7, p7 = stats.ttest_ind(retro_7d, direct_7d)

    return {
        "retrograde": {
            "days": len(retro),
            "mean_daily": round(retro.mean(), 4),
            "median_daily": round(retro.median(), 4),
            "positive_pct": round((retro > 0).mean() * 100, 1),
            "volatility": round(retro.std(), 4),
            "mean_7d": round(retro_7d.mean(), 4),
        },
        "direct": {
            "days": len(direct),
            "mean_daily": round(direct.mean(), 4),
            "median_daily": round(direct.median(), 4),
            "positive_pct": round((direct > 0).mean() * 100, 1),
            "volatility": round(direct.std(), 4),
            "mean_7d": round(direct_7d.mean(), 4),
        },
        "t_stat_daily": round(t_stat, 3),
        "p_value_daily": round(p_value, 4),
        "t_stat_7d": round(t7, 3),
        "p_value_7d": round(p7, 4),
    }


def analyze_eclipses(df: pd.DataFrame) -> dict:
    """Анализ поведения цены вокруг затмений."""
    in_window = df[df["eclipse_window"]]["return_pct"].dropna()
    outside = df[~df["eclipse_window"]]["return_pct"].dropna()

    t_stat, p_value = stats.ttest_ind(in_window, outside)

    # Волатильность
    vol_in = df[df["eclipse_window"]]["volatility"].dropna()
    vol_out = df[~df["eclipse_window"]]["volatility"].dropna()
    t_vol, p_vol = stats.ttest_ind(vol_in, vol_out)

    # Анализ по конкретным затмениям
    eclipse_events = []
    for date_str, etype in ECLIPSES:
        edate = pd.Timestamp(date_str)
        mask = (df["date"] >= edate - timedelta(days=7)) & (df["date"] <= edate + timedelta(days=7))
        window = df[mask]
        if len(window) >= 5:
            ret = window["close"].iloc[-1] / window["close"].iloc[0] * 100 - 100
            eclipse_events.append({
                "date": date_str,
                "type": etype,
                "return_14d": round(ret, 2),
                "price_at_eclipse": round(window["close"].iloc[len(window)//2], 0),
            })

    return {
        "window_7d": {
            "days": len(in_window),
            "mean_return": round(in_window.mean(), 4),
            "volatility": round(in_window.std(), 4),
            "positive_pct": round((in_window > 0).mean() * 100, 1),
        },
        "outside": {
            "days": len(outside),
            "mean_return": round(outside.mean(), 4),
            "volatility": round(outside.std(), 4),
            "positive_pct": round((outside > 0).mean() * 100, 1),
        },
        "t_stat": round(t_stat, 3),
        "p_value": round(p_value, 4),
        "volatility_t_stat": round(t_vol, 3),
        "volatility_p_value": round(p_vol, 4),
        "events": eclipse_events,
    }


def analyze_aspects(df: pd.DataFrame) -> dict:
    """Анализ влияния планетарных аспектов."""
    results = {}

    for aspect in ["has_square", "has_conjunction", "has_opposition", "has_trine"]:
        yes = df[df[aspect]]["return_pct"].dropna()
        no = df[~df[aspect]]["return_pct"].dropna()
        t_stat, p_value = stats.ttest_ind(yes, no)

        results[aspect.replace("has_", "")] = {
            "days_with": len(yes),
            "mean_with": round(yes.mean(), 4),
            "mean_without": round(no.mean(), 4),
            "diff": round(yes.mean() - no.mean(), 4),
            "t_stat": round(t_stat, 3),
            "p_value": round(p_value, 4),
            "significant": p_value < 0.05,
        }

    return results


# ============================================================
# 5. ВИЗУАЛИЗАЦИЯ
# ============================================================

def plot_results(df: pd.DataFrame, moon_results, mercury_results, eclipse_results, signs_df):
    """Строит графики результатов."""
    fig, axes = plt.subplots(2, 3, figsize=(24, 14))

    # 1. Доходность по фазам Луны
    ax = axes[0, 0]
    phases = list(moon_results.keys())
    means = [moon_results[p]["mean_return"] for p in phases]
    colors = ["#2196F3" if m >= 0 else "#F44336" for m in means]
    phase_labels = {"new_moon": "Новолуние", "waxing": "Растущая", "full_moon": "Полнолуние", "waning": "Убывающая"}
    bars = ax.bar([phase_labels[p] for p in phases], means, color=colors, edgecolor="black", linewidth=0.5)
    for bar, phase in zip(bars, phases):
        p_val = moon_results[phase]["p_value"]
        sig = "*" if p_val < 0.05 else ""
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                f"p={p_val:.3f}{sig}", ha="center", va="bottom", fontsize=9)
    ax.set_title("Средняя дневная доходность BTC по фазам Луны", fontsize=12, fontweight="bold")
    ax.set_ylabel("Доходность (%)")
    ax.axhline(y=0, color="gray", linewidth=0.5)
    ax.grid(axis="y", alpha=0.3)

    # 2. Меркурий ретроградный
    ax = axes[0, 1]
    labels = ["Ретроградный", "Директный"]
    means = [mercury_results["retrograde"]["mean_daily"], mercury_results["direct"]["mean_daily"]]
    vols = [mercury_results["retrograde"]["volatility"], mercury_results["direct"]["volatility"]]
    x = range(len(labels))
    bars = ax.bar(x, means, color=["#FF6B6B", "#4ECDC4"], edgecolor="black", linewidth=0.5, label="Доходность")
    ax2 = ax.twinx()
    ax2.plot(x, vols, "ko-", markersize=8, label="Волатильность")
    ax2.set_ylabel("Волатильность (%)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_title(f"Меркурий: ретро vs директ\np={mercury_results['p_value_daily']:.4f}", fontsize=12, fontweight="bold")
    ax.set_ylabel("Доходность (%)")
    ax.axhline(y=0, color="gray", linewidth=0.5)

    # 3. Знаки Луны
    ax = axes[0, 2]
    if not signs_df.empty:
        colors = ["#4CAF50" if v >= 0 else "#F44336" for v in signs_df["mean_return"]]
        ax.barh(signs_df["sign"], signs_df["mean_return"], color=colors, edgecolor="black", linewidth=0.5)
        for i, row in signs_df.iterrows():
            sig = " *" if row["p_value"] < 0.05 else ""
            ax.text(row["mean_return"], list(signs_df["sign"]).index(row["sign"]),
                    f" p={row['p_value']:.2f}{sig}", va="center", fontsize=8)
    ax.set_title("Средняя доходность BTC по знакам Луны", fontsize=12, fontweight="bold")
    ax.set_xlabel("Доходность (%)")
    ax.axvline(x=0, color="gray", linewidth=0.5)

    # 4. Затмения — доходность ±7 дней
    ax = axes[1, 0]
    events = eclipse_results["events"]
    if events:
        dates = [e["date"] for e in events]
        returns = [e["return_14d"] for e in events]
        colors = ["#FF9800" if e["type"] == "solar" else "#9C27B0" for e in events]
        ax.bar(range(len(dates)), returns, color=colors, edgecolor="black", linewidth=0.5)
        ax.set_xticks(range(len(dates)))
        ax.set_xticklabels([d[5:] for d in dates], rotation=45, fontsize=7)
        ax.axhline(y=0, color="gray", linewidth=0.5)
    ax.set_title(f"BTC доходность ±7д от затмений\np={eclipse_results['p_value']:.4f}", fontsize=12, fontweight="bold")
    ax.set_ylabel("Доходность за 14 дней (%)")

    # 5. Фаза Луны vs доходность (scatter)
    ax = axes[1, 1]
    valid = df.dropna(subset=["moon_phase", "return_pct"])
    ax.scatter(valid["moon_phase"], valid["return_pct"], alpha=0.15, s=8, color="#555")
    # Бины по фазе
    bins = pd.cut(valid["moon_phase"], bins=20)
    grouped = valid.groupby(bins, observed=True)["return_pct"].mean()
    bin_centers = [(b.left + b.right) / 2 for b in grouped.index]
    ax.plot(bin_centers, grouped.values, "r-", linewidth=2, label="Средняя по бинам")
    ax.axhline(y=0, color="gray", linewidth=0.5)
    ax.set_xlabel("Фаза Луны (0=новая, 0.5=полная, 1=новая)")
    ax.set_ylabel("Дневная доходность (%)")
    ax.set_title("Фаза Луны vs дневная доходность", fontsize=12, fontweight="bold")
    ax.legend()

    # 6. Волатильность: затмения vs обычные дни
    ax = axes[1, 2]
    vol_eclipse = df[df["eclipse_window"]]["volatility"].dropna()
    vol_normal = df[~df["eclipse_window"]]["volatility"].dropna()
    ax.boxplot([vol_normal, vol_eclipse], labels=["Обычные дни", "±7д от затмения"])
    ax.set_title(f"Волатильность: затмения vs обычные\np={eclipse_results['volatility_p_value']:.4f}",
                 fontsize=12, fontweight="bold")
    ax.set_ylabel("7-дневная волатильность (%)")

    plt.suptitle("BTC x Астрология: Корреляционный анализ 2020-2026", fontsize=18, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig("astro_btc_results.png", dpi=150, bbox_inches="tight")
    print("График сохранён: astro_btc_results.png")
    plt.close()


# ============================================================
# 6. ОТЧЁТ
# ============================================================

def print_report(moon_results, mercury_results, eclipse_results, signs_df, aspects_results):
    """Выводит полный отчёт."""
    print("\n" + "=" * 90)
    print("BTC x АСТРОЛОГИЯ — КОРРЕЛЯЦИОННЫЙ АНАЛИЗ 2020-2026")
    print("=" * 90)
    print("Методология: t-test (двухвыборочный), уровень значимости α = 0.05")
    print("p < 0.05 = статистически значимо (*), p < 0.01 = высоко значимо (**)")

    # --- ФАЗЫ ЛУНЫ ---
    print("\n\n" + "-" * 70)
    print("1. ФАЗЫ ЛУНЫ")
    print("-" * 70)
    phase_names = {"new_moon": "Новолуние", "waxing": "Растущая", "full_moon": "Полнолуние", "waning": "Убывающая"}
    print(f"{'Фаза':<15} {'Дней':>6} {'Ср.дох%':>10} {'Медиана':>10} {'Полож%':>8} {'Волат':>8} {'p-value':>10} {'Знач.':>6}")
    for phase, data in moon_results.items():
        sig = "**" if data["p_value"] < 0.01 else "*" if data["p_value"] < 0.05 else ""
        print(f"{phase_names[phase]:<15} {data['count']:>6} {data['mean_return']:>+10.4f} "
              f"{data['median_return']:>10.4f} {data['positive_pct']:>7.1f}% {data['volatility']:>8.4f} "
              f"{data['p_value']:>10.4f} {sig:>6}")

    # --- МЕРКУРИЙ ---
    print("\n\n" + "-" * 70)
    print("2. РЕТРОГРАДНЫЙ МЕРКУРИЙ")
    print("-" * 70)
    r = mercury_results
    print(f"{'Состояние':<15} {'Дней':>6} {'Ср.дох%':>10} {'Медиана':>10} {'Полож%':>8} {'Волат':>8} {'7д дох%':>10}")
    print(f"{'Ретроградный':<15} {r['retrograde']['days']:>6} {r['retrograde']['mean_daily']:>+10.4f} "
          f"{r['retrograde']['median_daily']:>10.4f} {r['retrograde']['positive_pct']:>7.1f}% "
          f"{r['retrograde']['volatility']:>8.4f} {r['retrograde']['mean_7d']:>+10.4f}")
    print(f"{'Директный':<15} {r['direct']['days']:>6} {r['direct']['mean_daily']:>+10.4f} "
          f"{r['direct']['median_daily']:>10.4f} {r['direct']['positive_pct']:>7.1f}% "
          f"{r['direct']['volatility']:>8.4f} {r['direct']['mean_7d']:>+10.4f}")
    sig_d = "**" if r["p_value_daily"] < 0.01 else "*" if r["p_value_daily"] < 0.05 else "нет"
    sig_7 = "**" if r["p_value_7d"] < 0.01 else "*" if r["p_value_7d"] < 0.05 else "нет"
    print(f"\n  Дневная доходность: t={r['t_stat_daily']:.3f}, p={r['p_value_daily']:.4f} — значимость: {sig_d}")
    print(f"  7-дневная доходность: t={r['t_stat_7d']:.3f}, p={r['p_value_7d']:.4f} — значимость: {sig_7}")

    # --- ЗНАКИ ЛУНЫ ---
    print("\n\n" + "-" * 70)
    print("3. ЛУНА В ЗНАКАХ ЗОДИАКА")
    print("-" * 70)
    print(f"{'Знак':<12} {'Дней':>6} {'Ср.дох%':>10} {'Медиана':>10} {'Полож%':>8} {'vs сред':>10} {'p-value':>10}")
    for _, row in signs_df.iterrows():
        sig = "**" if row["p_value"] < 0.01 else "*" if row["p_value"] < 0.05 else ""
        print(f"{row['sign']:<12} {row['count']:>6} {row['mean_return']:>+10.4f} "
              f"{row['median_return']:>10.4f} {row['positive_pct']:>7.1f}% "
              f"{row['vs_average']:>+10.4f} {row['p_value']:>10.4f} {sig}")

    # --- ЗАТМЕНИЯ ---
    print("\n\n" + "-" * 70)
    print("4. ЗАТМЕНИЯ (±7 дней)")
    print("-" * 70)
    e = eclipse_results
    print(f"  В окне затмения: дней={e['window_7d']['days']}, ср.доходность={e['window_7d']['mean_return']:+.4f}%, "
          f"волатильность={e['window_7d']['volatility']:.4f}")
    print(f"  Обычные дни:     дней={e['outside']['days']}, ср.доходность={e['outside']['mean_return']:+.4f}%, "
          f"волатильность={e['outside']['volatility']:.4f}")
    sig_e = "**" if e["p_value"] < 0.01 else "*" if e["p_value"] < 0.05 else "нет"
    print(f"\n  Доходность: p={e['p_value']:.4f} — значимость: {sig_e}")
    sig_v = "**" if e["volatility_p_value"] < 0.01 else "*" if e["volatility_p_value"] < 0.05 else "нет"
    print(f"  Волатильность: p={e['volatility_p_value']:.4f} — значимость: {sig_v}")

    print("\n  Конкретные затмения:")
    print(f"  {'Дата':<12} {'Тип':<8} {'Цена BTC':>12} {'Доход ±7д':>12}")
    for ev in e["events"]:
        print(f"  {ev['date']:<12} {ev['type']:<8} ${ev['price_at_eclipse']:>10,.0f} {ev['return_14d']:>+11.2f}%")

    # --- АСПЕКТЫ ---
    print("\n\n" + "-" * 70)
    print("5. ПЛАНЕТАРНЫЕ АСПЕКТЫ")
    print("-" * 70)
    print(f"{'Аспект':<15} {'Дней':>6} {'Ср.дох с':>10} {'Ср.дох без':>12} {'Разница':>10} {'p-value':>10} {'Знач.':>6}")
    aspect_names = {"conjunction": "Соединение", "square": "Квадратура", "opposition": "Оппозиция", "trine": "Трин"}
    for aspect, data in aspects_results.items():
        sig = "**" if data["p_value"] < 0.01 else "*" if data["p_value"] < 0.05 else ""
        print(f"{aspect_names.get(aspect, aspect):<15} {data['days_with']:>6} {data['mean_with']:>+10.4f} "
              f"{data['mean_without']:>+12.4f} {data['diff']:>+10.4f} {data['p_value']:>10.4f} {sig:>6}")

    # --- ИТОГ ---
    print("\n\n" + "=" * 90)
    print("ВЫВОДЫ")
    print("=" * 90)

    significant_findings = []
    for phase, data in moon_results.items():
        if data["significant"]:
            significant_findings.append(f"Фаза Луны '{phase_names[phase]}': p={data['p_value']:.4f}")

    if mercury_results["p_value_daily"] < 0.05:
        significant_findings.append(f"Меркурий ретро (дневная): p={mercury_results['p_value_daily']:.4f}")
    if mercury_results["p_value_7d"] < 0.05:
        significant_findings.append(f"Меркурий ретро (7-дневная): p={mercury_results['p_value_7d']:.4f}")

    if eclipse_results["p_value"] < 0.05:
        significant_findings.append(f"Затмения (доходность): p={eclipse_results['p_value']:.4f}")
    if eclipse_results["volatility_p_value"] < 0.05:
        significant_findings.append(f"Затмения (волатильность): p={eclipse_results['volatility_p_value']:.4f}")

    for _, row in signs_df.iterrows():
        if row["p_value"] < 0.05:
            significant_findings.append(f"Луна в {row['sign']}: p={row['p_value']:.4f}")

    for aspect, data in aspects_results.items():
        if data["significant"]:
            significant_findings.append(f"Аспект '{aspect_names.get(aspect, aspect)}': p={data['p_value']:.4f}")

    if significant_findings:
        print("\nСтатистически значимые находки (p < 0.05):")
        for f in significant_findings:
            print(f"  * {f}")
    else:
        print("\nНи один астрологический фактор не показал статистически значимой")
        print("корреляции с ценой BTC при уровне значимости α = 0.05.")

    print("\nВажно: даже при p < 0.05 это может быть случайность (множественное тестирование).")
    print("Поправка Бонферрони для ~30 тестов: α_adjusted = 0.05/30 ≈ 0.0017")


# ============================================================
# MAIN
# ============================================================

def main():
    df = load_btc_data()
    print(f"BTC данные: {len(df)} дней ({df['date'].min().date()} — {df['date'].max().date()})")

    df = build_astro_dataframe(df)

    # Анализ
    print("\nЗапуск статистического анализа...")
    moon_results = analyze_moon_phases(df)
    signs_df = analyze_moon_signs(df)
    mercury_results = analyze_mercury_retrograde(df)
    eclipse_results = analyze_eclipses(df)
    aspects_results = analyze_aspects(df)

    # Отчёт
    print_report(moon_results, mercury_results, eclipse_results, signs_df, aspects_results)

    # Графики
    plot_results(df, moon_results, mercury_results, eclipse_results, signs_df)

    # Сохраняем в БД
    conn = duckdb.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS btc_astro (
            date TEXT PRIMARY KEY,
            close REAL,
            return_pct REAL,
            moon_phase REAL,
            moon_quarter TEXT,
            moon_sign TEXT,
            mercury_retro INTEGER,
            eclipse_days INTEGER,
            n_aspects INTEGER
        )
    """)
    conn.execute("DELETE FROM btc_astro")

    records = []
    for _, row in df.iterrows():
        records.append((
            row["date"].strftime("%Y-%m-%d"),
            row["close"],
            row["return_pct"] if pd.notna(row["return_pct"]) else None,
            row["moon_phase"],
            row["moon_quarter"],
            row["moon_sign"],
            int(row["mercury_retro"]),
            row["eclipse_days"],
            row["n_aspects"],
        ))
    conn.executemany("INSERT INTO btc_astro VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", records)
    conn.commit()
    conn.close()
    print(f"\nАстро-данные сохранены в БД: таблица btc_astro ({len(records)} строк)")


if __name__ == "__main__":
    main()
