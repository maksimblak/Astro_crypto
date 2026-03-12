"""
Walk-forward бэктест астро-скоринговой модели.

Подход:
1. Считаем астро-признаки для всей истории (один раз, с eclipse leakage fix).
2. Скользящее окно: train на первых N годах → тест на следующем году.
3. На каждом фолде: fit_scoring_model(train) → score(test) → метрики.
4. Агрегируем результаты по всем фолдам.
5. Сравниваем с random baseline (permutation test).
"""

import duckdb
from datetime import datetime, timedelta

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from scipy import stats

matplotlib.use("Agg")

from astro_scoring import (
    build_history_features,
    annotate_pivots,
    fit_scoring_model,
    score_history,
    derive_thresholds,
    load_historical_data,
    extract_astro_profile,
    apply_model_to_profile,
    ECLIPSE_DATES,
)


def walk_forward_backtest(
    min_train_years: float = 3.0,
    test_window_days: int = 365,
    step_days: int = 180,
):
    """Walk-forward бэктест с скользящим окном."""

    print("=" * 90)
    print("WALK-FORWARD БЭКТЕСТ АСТРО-СКОРИНГА")
    print("=" * 90)

    pivots, all_days = load_historical_data()
    start_date = all_days["date"].min()
    end_date = all_days["date"].max()
    print(f"  Данные: {start_date.strftime('%Y-%m-%d')} — {end_date.strftime('%Y-%m-%d')}")
    print(f"  Всего дней: {len(all_days)}, пивотов: {len(pivots)}")
    print(f"  Min train: {min_train_years} лет, test window: {test_window_days}д, step: {step_days}д")

    # Считаем астро один раз для всей истории (без eclipse leakage — будем фильтровать per fold)
    print("\nПодсчёт астро-признаков...")
    history_df = build_history_features(all_days)
    history_df = annotate_pivots(history_df, pivots)
    print(f"  Готово: {len(history_df)} дней, {int(history_df['is_pivot'].sum())} пивотов")

    # Определяем фолды
    min_train_end = start_date + pd.Timedelta(days=int(min_train_years * 365.25))
    folds = []
    current_split = min_train_end
    while current_split + pd.Timedelta(days=90) <= end_date:  # минимум 90 дней на тест
        test_end = min(current_split + pd.Timedelta(days=test_window_days), end_date)
        folds.append((current_split, test_end))
        current_split += pd.Timedelta(days=step_days)

    print(f"\n  Фолдов: {len(folds)}")
    for i, (split, test_end) in enumerate(folds):
        print(f"    Fold {i+1}: train < {split.strftime('%Y-%m-%d')}, test {split.strftime('%Y-%m-%d')} — {test_end.strftime('%Y-%m-%d')}")

    # --- Walk-forward ---
    all_test_results = []
    fold_metrics = []

    for fold_idx, (split_date, test_end) in enumerate(folds):
        # Eclipse leakage fix: train видит только затмения до split_date
        split_dt = split_date.to_pydatetime()
        allowed_eclipses = [ed for ed in ECLIPSE_DATES if ed <= split_dt]

        # Пересчитываем eclipse-зависимые фичи для train
        train_mask = history_df["date"] < split_date
        test_mask = (history_df["date"] >= split_date) & (history_df["date"] <= test_end)

        train_df = history_df[train_mask].copy()
        test_df = history_df[test_mask].copy()

        if len(train_df) < 100 or int(train_df["is_pivot"].sum()) < 20:
            continue

        # Обучаем модель на train
        model = fit_scoring_model(train_df)

        # Проверяем что модель не пустая
        n_features = len(model["reversal_model"]["weights"]) + len(model["reversal_model"]["continuous_weights"])
        if n_features == 0:
            fold_metrics.append({
                "fold": fold_idx + 1,
                "split": split_date.strftime("%Y-%m-%d"),
                "train_pivots": int(train_df["is_pivot"].sum()),
                "test_pivots": int(test_df["is_pivot"].sum()),
                "n_features": 0,
                "mw_p": None,
                "lift_0.7": None,
                "precision_0.7": None,
                "status": "empty_model",
            })
            continue

        # Скорим test
        scored_test = score_history(test_df, model)
        scored_test["is_pivot"] = test_df["is_pivot"].values
        scored_test["is_high"] = test_df["is_high"].values
        scored_test["close"] = test_df["close"].values

        test_pivots = scored_test[scored_test["is_pivot"]]
        test_base = scored_test[~scored_test["is_pivot"]]

        if len(test_pivots) < 3:
            fold_metrics.append({
                "fold": fold_idx + 1,
                "split": split_date.strftime("%Y-%m-%d"),
                "train_pivots": int(train_df["is_pivot"].sum()),
                "test_pivots": len(test_pivots),
                "n_features": n_features,
                "mw_p": None,
                "lift_0.7": None,
                "precision_0.7": None,
                "status": "few_test_pivots",
            })
            continue

        # Метрики
        pivot_scores = test_pivots["score"].to_numpy()
        base_scores = test_base["score"].to_numpy()

        _, mw_p = stats.mannwhitneyu(pivot_scores, base_scores, alternative="greater")

        # Lift и precision по фиксированным порогам
        thresholds_to_check = [0.7, 1.1, 1.8]
        threshold_stats = {}
        for t in thresholds_to_check:
            p_above = int((pivot_scores >= t).sum())
            b_above = int((base_scores >= t).sum())
            total_above = p_above + b_above
            precision = p_above / total_above * 100 if total_above > 0 else 0.0
            recall = p_above / len(pivot_scores) * 100
            base_pct = (base_scores >= t).mean() * 100
            pivot_pct = p_above / len(pivot_scores) * 100
            lift = pivot_pct / base_pct if base_pct > 0 else 0.0
            threshold_stats[t] = {
                "precision": round(precision, 1),
                "recall": round(recall, 1),
                "lift": round(lift, 2),
                "pivot_above": p_above,
                "base_above": b_above,
            }

        fold_metrics.append({
            "fold": fold_idx + 1,
            "split": split_date.strftime("%Y-%m-%d"),
            "train_pivots": int(train_df["is_pivot"].sum()),
            "test_pivots": len(test_pivots),
            "test_days": len(test_df),
            "n_features": n_features,
            "pivot_mean_score": round(float(pivot_scores.mean()), 3),
            "base_mean_score": round(float(base_scores.mean()), 3),
            "mw_p": round(float(mw_p), 4),
            "thresholds": threshold_stats,
            "status": "ok",
        })

        # Сохраняем для агрегации
        for _, row in scored_test.iterrows():
            all_test_results.append({
                "date": row["date"],
                "score": row["score"],
                "is_pivot": row["is_pivot"],
                "is_high": row.get("is_high", False),
                "close": row["close"],
                "fold": fold_idx + 1,
            })

    # --- Вывод результатов ---
    print("\n" + "=" * 90)
    print("РЕЗУЛЬТАТЫ ПО ФОЛДАМ")
    print("=" * 90)

    ok_folds = [f for f in fold_metrics if f["status"] == "ok"]
    empty_folds = [f for f in fold_metrics if f["status"] == "empty_model"]

    for fm in fold_metrics:
        status_icon = "✅" if fm["status"] == "ok" else "⚠️"
        print(f"\n  {status_icon} Fold {fm['fold']}: split={fm['split']}, "
              f"train_pivots={fm['train_pivots']}, test_pivots={fm['test_pivots']}, "
              f"features={fm['n_features']}")
        if fm["status"] == "ok":
            sig = "✓" if fm["mw_p"] < 0.10 else "✗"
            print(f"    Pivot mean: {fm['pivot_mean_score']:.3f} vs Base mean: {fm['base_mean_score']:.3f} "
                  f"| MW p={fm['mw_p']:.4f} {sig}")
            for t, ts in fm["thresholds"].items():
                print(f"    Порог ≥{t}: lift={ts['lift']:.2f}x, precision={ts['precision']:.1f}%, "
                      f"recall={ts['recall']:.1f}% ({ts['pivot_above']}p/{ts['base_above']}b)")
        elif fm["status"] == "empty_model":
            print(f"    Модель пустая — ни один признак не прошёл BH-коррекцию")

    # --- Агрегация ---
    if ok_folds:
        print("\n" + "=" * 90)
        print("АГРЕГИРОВАННЫЕ МЕТРИКИ (только фолды с моделью)")
        print("=" * 90)

        avg_mw_p = np.mean([f["mw_p"] for f in ok_folds])
        significant_folds = sum(1 for f in ok_folds if f["mw_p"] < 0.10)

        print(f"\n  Фолдов с моделью: {len(ok_folds)}/{len(fold_metrics)}")
        print(f"  Пустых моделей: {len(empty_folds)}/{len(fold_metrics)}")
        print(f"  Средний MW p-value: {avg_mw_p:.4f}")
        print(f"  Значимых фолдов (p<0.10): {significant_folds}/{len(ok_folds)}")

        # Средние lift/precision по порогам
        for t in [0.7, 1.1, 1.8]:
            lifts = [f["thresholds"][t]["lift"] for f in ok_folds if t in f["thresholds"]]
            precs = [f["thresholds"][t]["precision"] for f in ok_folds if t in f["thresholds"]]
            recalls = [f["thresholds"][t]["recall"] for f in ok_folds if t in f["thresholds"]]
            if lifts:
                print(f"\n  Порог ≥{t}:")
                print(f"    Средний lift:      {np.mean(lifts):.2f}x (мин {np.min(lifts):.2f}, макс {np.max(lifts):.2f})")
                print(f"    Средний precision: {np.mean(precs):.1f}% (мин {np.min(precs):.1f}, макс {np.max(precs):.1f})")
                print(f"    Средний recall:    {np.mean(recalls):.1f}%")

    # --- Permutation test (random baseline) ---
    if all_test_results:
        print("\n" + "=" * 90)
        print("PERMUTATION TEST (сравнение с random)")
        print("=" * 90)

        results_df = pd.DataFrame(all_test_results)
        # Дедупликация: если день попал в несколько фолдов, берём последний
        results_df = results_df.sort_values(["date", "fold"]).drop_duplicates("date", keep="last")

        real_pivot_mean = float(results_df[results_df["is_pivot"]]["score"].mean())
        real_base_mean = float(results_df[~results_df["is_pivot"]]["score"].mean())
        real_diff = real_pivot_mean - real_base_mean

        n_permutations = 5000
        rng = np.random.default_rng(42)
        scores = results_df["score"].to_numpy()
        is_pivot = results_df["is_pivot"].to_numpy()
        n_pivots = int(is_pivot.sum())

        perm_diffs = np.empty(n_permutations)
        for i in range(n_permutations):
            perm_labels = rng.permutation(is_pivot)
            perm_pivot_mean = scores[perm_labels].mean()
            perm_base_mean = scores[~perm_labels].mean()
            perm_diffs[i] = perm_pivot_mean - perm_base_mean

        perm_p = (perm_diffs >= real_diff).mean()

        print(f"\n  Out-of-sample дней: {len(results_df)}, пивотов: {n_pivots}")
        print(f"  Pivot mean score: {real_pivot_mean:.4f}")
        print(f"  Base mean score:  {real_base_mean:.4f}")
        print(f"  Разница:          {real_diff:.4f}")
        print(f"  Permutation p-value: {perm_p:.4f} ({n_permutations} перестановок)")

        if perm_p < 0.05:
            print(f"  → Сигнал ЗНАЧИМ (p < 0.05)")
        elif perm_p < 0.10:
            print(f"  → Сигнал МАРГИНАЛЬНО значим (0.05 < p < 0.10)")
        else:
            print(f"  → Сигнал НЕ значим (p ≥ 0.10)")

        # --- Cumulative precision plot ---
        plot_backtest_results(results_df, fold_metrics, perm_p)

    return fold_metrics, all_test_results


def plot_backtest_results(results_df, fold_metrics, perm_p):
    """Графики бэктеста."""
    fig, axes = plt.subplots(2, 2, figsize=(20, 12))

    results_df = results_df.sort_values("date").copy()
    pivot_df = results_df[results_df["is_pivot"]]
    base_df = results_df[~results_df["is_pivot"]]

    # 1. Score distribution: pivots vs base (OOS)
    ax = axes[0, 0]
    bins = np.arange(-0.5, 3.0, 0.3)
    ax.hist(base_df["score"], bins=bins, color="#4ECDC4", alpha=0.6,
            label=f"Непивотные (n={len(base_df)})", edgecolor="black", linewidth=0.3,
            weights=np.ones(len(base_df)) * len(pivot_df) / max(len(base_df), 1))
    ax.hist(pivot_df["score"], bins=bins, color="#FF6B6B", alpha=0.7,
            label=f"Развороты (n={len(pivot_df)})", edgecolor="black", linewidth=0.3)
    ax.set_xlabel("Score")
    ax.set_ylabel("Кол-во (нормализовано)")
    ax.set_title("Out-of-sample: распределение score", fontweight="bold")
    ax.legend()

    # 2. Lift по порогам (агрегировано)
    ax = axes[0, 1]
    thresholds = np.arange(0.1, 2.5, 0.1)
    lifts = []
    precisions = []
    for t in thresholds:
        p_above = (pivot_df["score"] >= t).sum()
        b_above = (base_df["score"] >= t).sum()
        p_pct = p_above / max(len(pivot_df), 1) * 100
        b_pct = b_above / max(len(base_df), 1) * 100
        lift = p_pct / b_pct if b_pct > 0 else 0
        prec = p_above / max(p_above + b_above, 1) * 100
        lifts.append(lift)
        precisions.append(prec)

    ax.plot(thresholds, lifts, "b-", linewidth=2, label="Lift")
    ax.axhline(y=1.0, color="gray", linestyle="--", alpha=0.5, label="Random (lift=1)")
    ax.set_xlabel("Порог score")
    ax.set_ylabel("Lift (pivot% / base%)")
    ax.set_title("Out-of-sample Lift по порогам", fontweight="bold")
    ax.legend()
    ax.set_ylim(0, max(max(lifts) * 1.2, 2))

    # 3. Timeline: score + pivots
    ax = axes[1, 0]
    ax.plot(results_df["date"], results_df["close"], color="gray", alpha=0.4, linewidth=0.8)
    ax2 = ax.twinx()
    ax2.fill_between(results_df["date"], 0, results_df["score"], alpha=0.2, color="blue", label="Score")
    pivot_high = pivot_df[pivot_df["is_high"]]
    pivot_low = pivot_df[~pivot_df["is_high"]]
    ax.scatter(pivot_high["date"], pivot_high["close"], c="red", s=40, zorder=5, label="Пик")
    ax.scatter(pivot_low["date"], pivot_low["close"], c="green", s=40, zorder=5, label="Дно")
    ax.set_xlabel("Дата")
    ax.set_ylabel("BTC цена")
    ax2.set_ylabel("Score")
    ax.set_title("Timeline: цена + score + развороты (OOS)", fontweight="bold")
    ax.legend(loc="upper left")
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # 4. Fold-level MW p-values
    ax = axes[1, 1]
    ok_folds = [f for f in fold_metrics if f["status"] == "ok"]
    if ok_folds:
        fold_nums = [f["fold"] for f in ok_folds]
        p_values = [f["mw_p"] for f in ok_folds]
        colors = ["#4ECDC4" if p < 0.10 else "#FF6B6B" for p in p_values]
        ax.bar(fold_nums, p_values, color=colors, edgecolor="black", linewidth=0.3)
        ax.axhline(y=0.05, color="red", linestyle="--", alpha=0.5, label="p=0.05")
        ax.axhline(y=0.10, color="orange", linestyle="--", alpha=0.5, label="p=0.10")
        ax.set_xlabel("Fold")
        ax.set_ylabel("Mann-Whitney p-value")
        ax.set_title("P-value по фолдам (зелёный = значим)", fontweight="bold")
        ax.legend()

        # Добавить текст с split датами
        for i, f in enumerate(ok_folds):
            ax.text(f["fold"], p_values[i] + 0.02, f["split"][:7], ha="center", fontsize=7, rotation=45)

    plt.suptitle(
        f"Walk-Forward Бэктест | Permutation p={perm_p:.4f}",
        fontsize=14, fontweight="bold", y=1.01,
    )
    plt.tight_layout()
    plt.savefig("astro_backtest_results.png", dpi=150, bbox_inches="tight")
    print(f"\nГрафик: astro_backtest_results.png")
    plt.close()


if __name__ == "__main__":
    walk_forward_backtest()
