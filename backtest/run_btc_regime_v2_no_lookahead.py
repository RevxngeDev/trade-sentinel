from __future__ import annotations

import warnings
from itertools import product
from typing import Any

import pandas as pd

from app.core.signals import build_regime_signals
from backtest.common import DATA_DIR, load_pair_data
from backtest.engine import build_metrics, run_position_backtest


warnings.filterwarnings("ignore", category=FutureWarning)

SYMBOL = "BTC/USDT"

RESULTS_PATH = DATA_DIR / "btc_regime_v2_no_lookahead_results.csv"
SELECTED_PATH = DATA_DIR / "btc_regime_v2_no_lookahead_selected.csv"
WALK_FORWARD_PATH = DATA_DIR / "btc_regime_v2_no_lookahead_walk_forward.csv"
WALK_FORWARD_SUMMARY_PATH = DATA_DIR / "btc_regime_v2_no_lookahead_walk_forward_summary.csv"
SELECTED_TRADES_PATH = DATA_DIR / "btc_regime_v2_no_lookahead_selected_trades.csv"
SELECTED_EQUITY_PATH = DATA_DIR / "btc_regime_v2_no_lookahead_selected_equity.csv"


# ============================================================
# Periodos y ventanas
# ============================================================

def split_train_test(
    df_1h: pd.DataFrame,
    df_4h: pd.DataFrame,
    train_ratio: float = 0.7,
) -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    split_index = int(len(df_1h) * train_ratio)
    split_timestamp = df_1h.index[split_index]

    return {
        "full": (df_1h.copy(), df_4h.copy()),
        "train": (df_1h.loc[:split_timestamp].copy(), df_4h.loc[:split_timestamp].copy()),
        "test": (df_1h.loc[split_timestamp:].copy(), df_4h.loc[split_timestamp:].copy()),
    }


def generate_walk_forward_windows(
    df_1h: pd.DataFrame,
    *,
    train_days: int = 270,
    test_days: int = 60,
) -> list[dict[str, Any]]:
    start = df_1h.index.min()
    end = df_1h.index.max()

    windows: list[dict[str, Any]] = []
    train_start = start
    fold = 1

    while True:
        train_end = train_start + pd.Timedelta(days=train_days)
        test_start = train_end
        test_end = test_start + pd.Timedelta(days=test_days)

        if test_end > end:
            break

        windows.append(
            {
                "fold": fold,
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
            }
        )

        train_start = train_start + pd.Timedelta(days=test_days)
        fold += 1

    return windows


# ============================================================
# Un backtest por configuración
# ============================================================

def run_config(
    *,
    period: str,
    df_1h: pd.DataFrame,
    df_4h: pd.DataFrame,
    entry_confirmation_bars: int,
    exit_confirmation_bars: int,
    cooldown_hours: int,
    min_hold_hours: int,
    exit_buffer_pct: float = 0.0,
    fold: int | None = None,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    signal_df = build_regime_signals(
        df_1h=df_1h,
        df_4h=df_4h,
        entry_confirmation_bars=entry_confirmation_bars,
        exit_confirmation_bars=exit_confirmation_bars,
        exit_buffer_pct=exit_buffer_pct,
    )

    trades_df, equity_curve_df = run_position_backtest(
        signal_df,
        symbol=SYMBOL,
        cooldown_hours=cooldown_hours,
        min_hold_hours=min_hold_hours,
    )

    metrics = build_metrics(df_1h=df_1h, trades_df=trades_df, equity_curve_df=equity_curve_df)

    row = {
        "fold": fold,
        "period": period,
        "symbol": SYMBOL,
        "strategy_name": "btc_regime_v2_no_lookahead",
        "entry_confirmation_bars": entry_confirmation_bars,
        "exit_confirmation_bars": exit_confirmation_bars,
        "cooldown_hours": cooldown_hours,
        "min_hold_hours": min_hold_hours,
        "exit_buffer_pct": exit_buffer_pct,
        **metrics,
        "selection_score": None,
    }

    return row, trades_df, equity_curve_df


# ============================================================
# Selección y grid
# ============================================================

def calculate_selection_score(row: pd.Series) -> float:
    def _num(key: str, default: float) -> float:
        value = row.get(key)
        return default if pd.isna(value) else float(value)

    total_return = _num("total_return_pct", 0)
    benchmark_return = _num("benchmark_return_pct", 0)
    max_drawdown = _num("max_drawdown_pct", 100)
    benchmark_drawdown = _num("benchmark_drawdown_pct", 100)
    profit_factor = _num("profit_factor", 0)
    total_trades = int(_num("total_trades", 0))
    exposure_pct = _num("exposure_pct", 0)

    excess_return = total_return - benchmark_return
    drawdown_improvement = benchmark_drawdown - max_drawdown

    score = 0.0
    score += total_return * 0.80
    score += excess_return * 0.60
    score += drawdown_improvement * 0.70
    score += profit_factor * 8.0

    # Queremos menos whipsaw, pero suficiente muestra.
    if 5 <= total_trades <= 35:
        score += 8
    elif total_trades < 5:
        score -= 15
    else:
        score -= (total_trades - 35) * 0.5

    # Exposición razonable para semi-pasivo.
    if 15 <= exposure_pct <= 70:
        score += 5
    elif exposure_pct < 10:
        score -= 8
    elif exposure_pct > 80:
        score -= 5

    if max_drawdown > 25:
        score -= 15
    if profit_factor < 1.0:
        score -= 10
    if total_return < 0:
        score -= 8

    return score


def build_grid() -> list[tuple[int, int, int, int, float]]:
    entry_confirmation_values = [1, 2, 3]
    exit_confirmation_values = [1, 2, 3]
    cooldown_values = [0, 12, 24, 48]
    min_hold_values = [0, 12, 24]
    # exit_buffer_pct == 0.0 reproduce el v2 base; > 0 exige ruptura real
    # del precio bajo la EMA50 antes de salir.
    exit_buffer_values = [0.0, 0.01, 0.02, 0.03]

    return list(
        product(
            entry_confirmation_values,
            exit_confirmation_values,
            cooldown_values,
            min_hold_values,
            exit_buffer_values,
        )
    )


def config_columns() -> list[str]:
    return [
        "entry_confirmation_bars",
        "exit_confirmation_bars",
        "cooldown_hours",
        "min_hold_hours",
        "exit_buffer_pct",
    ]


def filter_same_config(df: pd.DataFrame, selected_row: pd.Series) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    for col in config_columns():
        mask &= df[col] == selected_row[col]
    return df[mask].copy()


# ============================================================
# Walk-forward
# ============================================================

def run_walk_forward(
    df_1h: pd.DataFrame,
    df_4h: pd.DataFrame,
    grid: list[tuple[int, int, int, int, float]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    windows = generate_walk_forward_windows(df_1h, train_days=270, test_days=60)

    selected_tests: list[dict[str, Any]] = []

    print(f"\nVentanas walk-forward: {len(windows)}")

    for window in windows:
        fold = int(window["fold"])
        train_start, train_end = window["train_start"], window["train_end"]
        test_start, test_end = window["test_start"], window["test_end"]

        print(
            f"\n========== FOLD {fold} ==========\n"
            f"TRAIN: {train_start} -> {train_end}\n"
            f"TEST:  {test_start} -> {test_end}"
        )

        train_1h = df_1h.loc[train_start:train_end].copy()
        train_4h = df_4h.loc[train_start:train_end].copy()
        test_1h = df_1h.loc[test_start:test_end].copy()
        test_4h = df_4h.loc[test_start:test_end].copy()

        train_rows: list[dict[str, Any]] = []

        for index, combo in enumerate(grid, start=1):
            entry_conf, exit_conf, cooldown, min_hold, exit_buffer = combo

            if index == 1 or index % 25 == 0:
                print(f"Fold {fold}: config {index}/{len(grid)}")

            row, _, _ = run_config(
                period="train",
                df_1h=train_1h,
                df_4h=train_4h,
                entry_confirmation_bars=entry_conf,
                exit_confirmation_bars=exit_conf,
                cooldown_hours=cooldown,
                min_hold_hours=min_hold,
                exit_buffer_pct=exit_buffer,
                fold=fold,
            )

            row.update(
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
            train_rows.append(row)

        train_df = pd.DataFrame(train_rows)
        train_df["selection_score"] = train_df.apply(calculate_selection_score, axis=1)
        train_df = train_df.sort_values(by="selection_score", ascending=False)
        selected_train = train_df.iloc[0]

        test_row, _, _ = run_config(
            period="test",
            df_1h=test_1h,
            df_4h=test_4h,
            entry_confirmation_bars=int(selected_train["entry_confirmation_bars"]),
            exit_confirmation_bars=int(selected_train["exit_confirmation_bars"]),
            cooldown_hours=int(selected_train["cooldown_hours"]),
            min_hold_hours=int(selected_train["min_hold_hours"]),
            exit_buffer_pct=float(selected_train["exit_buffer_pct"]),
            fold=fold,
        )

        test_row.update(
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            train_total_return_pct=selected_train["total_return_pct"],
            train_benchmark_return_pct=selected_train["benchmark_return_pct"],
            train_max_drawdown_pct=selected_train["max_drawdown_pct"],
            train_profit_factor=selected_train["profit_factor"],
            train_total_trades=selected_train["total_trades"],
            train_exposure_pct=selected_train["exposure_pct"],
            train_selection_score=selected_train["selection_score"],
        )
        selected_tests.append(test_row)

        print("\nTEST result:")
        print(
            pd.Series(test_row)[
                config_columns()
                + [
                    "total_return_pct",
                    "benchmark_return_pct",
                    "max_drawdown_pct",
                    "profit_factor",
                    "total_trades",
                    "exposure_pct",
                    "profitable",
                    "beat_benchmark",
                ]
            ].to_string()
        )

    wf_df = pd.DataFrame(selected_tests)

    summary = {
        "folds": len(wf_df),
        "avg_test_return_pct": wf_df["total_return_pct"].mean(),
        "median_test_return_pct": wf_df["total_return_pct"].median(),
        "sum_test_return_pct_simple": wf_df["total_return_pct"].sum(),
        "avg_benchmark_return_pct": wf_df["benchmark_return_pct"].mean(),
        "sum_benchmark_return_pct_simple": wf_df["benchmark_return_pct"].sum(),
        "avg_strategy_drawdown_pct": wf_df["max_drawdown_pct"].mean(),
        "avg_benchmark_drawdown_pct": wf_df["benchmark_drawdown_pct"].mean(),
        "avg_profit_factor": wf_df["profit_factor"].mean(),
        "total_test_trades": wf_df["total_trades"].sum(),
        "avg_exposure_pct": wf_df["exposure_pct"].mean(),
        "profitable_folds": int(wf_df["profitable"].fillna(False).sum()),
        "beat_benchmark_folds": int(wf_df["beat_benchmark"].fillna(False).sum()),
    }

    return wf_df, pd.DataFrame([summary])


# ============================================================
# Main
# ============================================================

REPORT_COLUMNS = config_columns() + [
    "initial_equity",
    "final_equity",
    "total_return_pct",
    "benchmark_return_pct",
    "max_drawdown_pct",
    "benchmark_drawdown_pct",
    "total_trades",
    "wins",
    "losses",
    "win_rate_pct",
    "profit_factor",
    "exposure_pct",
    "profitable",
    "beat_benchmark",
    "selection_score",
]


def run_btc_regime_v2_no_lookahead() -> None:
    print("\n========== BTC REGIME V2 NO LOOKAHEAD ==========\n")

    print(f"Cargando datos para {SYMBOL}...")
    df_1h, df_4h = load_pair_data(SYMBOL)

    print(f"Velas 1h: {len(df_1h)} | 4h: {len(df_4h)}")
    print(f"Rango: {df_1h.index.min()} -> {df_1h.index.max()}")

    required = {"close", "ema_50", "ema_200", "rsi_14"}
    for name, frame in (("1h", df_1h), ("4h", df_4h)):
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"Faltan columnas en df_{name}: {missing}")

    periods = split_train_test(df_1h=df_1h, df_4h=df_4h, train_ratio=0.7)
    grid = build_grid()

    print(f"Combinaciones: {len(grid)} | backtests train/test/full: {len(grid) * 3}")

    all_rows: list[dict[str, Any]] = []

    for period_name, (period_df_1h, period_df_4h) in periods.items():
        print(f"\nProcesando periodo: {period_name}")

        for index, combo in enumerate(grid, start=1):
            entry_conf, exit_conf, cooldown, min_hold, exit_buffer = combo

            if index == 1 or index % 25 == 0:
                print(f"{period_name}: config {index}/{len(grid)}")

            row, _, _ = run_config(
                period=period_name,
                df_1h=period_df_1h,
                df_4h=period_df_4h,
                entry_confirmation_bars=entry_conf,
                exit_confirmation_bars=exit_conf,
                cooldown_hours=cooldown,
                min_hold_hours=min_hold,
                exit_buffer_pct=exit_buffer,
            )
            all_rows.append(row)

    results_df = pd.DataFrame(all_rows)

    train_mask = results_df["period"] == "train"
    results_df.loc[train_mask, "selection_score"] = (
        results_df.loc[train_mask].apply(calculate_selection_score, axis=1)
    )

    results_df.to_csv(RESULTS_PATH, index=False)

    train_candidates = (
        results_df[train_mask].copy().sort_values(by="selection_score", ascending=False)
    )
    selected_train = train_candidates.iloc[0]

    selected_all_periods = filter_same_config(results_df, selected_train)
    selected_all_periods.to_csv(SELECTED_PATH, index=False)

    _, selected_trades_df, selected_equity_df = run_config(
        period="full",
        df_1h=periods["full"][0],
        df_4h=periods["full"][1],
        entry_confirmation_bars=int(selected_train["entry_confirmation_bars"]),
        exit_confirmation_bars=int(selected_train["exit_confirmation_bars"]),
        cooldown_hours=int(selected_train["cooldown_hours"]),
        min_hold_hours=int(selected_train["min_hold_hours"]),
        exit_buffer_pct=float(selected_train["exit_buffer_pct"]),
    )

    selected_trades_df.to_csv(SELECTED_TRADES_PATH, index=False)
    selected_equity_df.to_csv(SELECTED_EQUITY_PATH)

    print("\n========== TOP 20 TRAIN CONFIGS ==========\n")
    print(train_candidates[REPORT_COLUMNS].head(20).to_string(index=False))

    print("\n========== SELECTED CONFIG ALL PERIODS ==========\n")
    print(selected_all_periods[REPORT_COLUMNS].to_string(index=False))

    print("\n========== WALK-FORWARD V2 ==========\n")
    wf_df, wf_summary_df = run_walk_forward(df_1h=df_1h, df_4h=df_4h, grid=grid)

    wf_df.to_csv(WALK_FORWARD_PATH, index=False)
    wf_summary_df.to_csv(WALK_FORWARD_SUMMARY_PATH, index=False)

    print("\n========== WALK-FORWARD SUMMARY ==========\n")
    print(wf_summary_df.to_string(index=False))

    print(f"\nResultados: {RESULTS_PATH}")
    print(f"Walk-forward: {WALK_FORWARD_PATH}")


if __name__ == "__main__":
    run_btc_regime_v2_no_lookahead()
