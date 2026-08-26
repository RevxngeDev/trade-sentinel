"""
Walk-forward no-lookahead POR ACTIVO (research offline).

Pregunta que responde: la config fija validada para BTC/USDT
(entry=2, exit=2, exit_buffer=0.02) ¿aguanta ventana a ventana en otros activos,
o su resultado multi-activo del full-period era un espejismo?

Contexto: `run_multi_asset_eval.py` (2026-06-30) aplicó esa config a 5 activos en
FULL PERIOD y salió positivo en 3/5. Pero en BTC ya vimos que el full-period
engaña: la selección por fold daba -10.6% mientras el full-period lucía bien.
Este script trocea cada activo en ventanas rodantes y evalúa SOLO los tramos de
test, que son contiguos y no se solapan (por eso se pueden componer).

Metodología:
- CONFIG FIJA para todos los activos y todos los folds. No hay selección por fold
  (eso fue precisamente lo que sobreajustó en BTC), así que la ventana de train no
  se optimiza: se usa solo para fijar el troceado temporal y que las ventanas de
  test coincidan con las del walk-forward de BTC.
- Los indicadores se calculan sobre el histórico completo y DESPUÉS se trocea. Son
  causales (EMA/RSI solo miran hacia atrás), así que esto equivale a una ventana
  expansiva y evita que cada fold arranque con indicadores sin calentar.
- Cada fold empieza FLAT (sin posición heredada) y cierra la posición abierta al
  final de su ventana. Es conservador y hace los folds independientes.
- Se reporta además el full-period de cada activo para comparar directamente
  "lo que dice el full-period" vs "lo que dice el walk-forward".

No toca el paper trading en vivo: solo lee CSV de data/ (o los refresca vía ccxt).

Uso:
    python -m backtest.run_multi_asset_walk_forward
    python -m backtest.run_multi_asset_walk_forward --refresh
    python -m backtest.run_multi_asset_walk_forward --assets BTC/USDT ETH/USDT
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.signals import build_regime_signals
from backtest.common import (
    DATA_DIR,
    FROZEN_DATA_DIR,
    generate_walk_forward_windows,
    load_pair_data,
)
from backtest.engine import build_metrics, run_position_backtest

warnings.filterwarnings("ignore", category=FutureWarning)

PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]

# La config determinista adoptada para BTC/USDT (ver DECISIONS.md 2026-06-21).
CONFIG = dict(
    entry_confirmation_bars=2,
    exit_confirmation_bars=2,
    exit_buffer_pct=0.02,
)
COOLDOWN_HOURS = 0
MIN_HOLD_HOURS = 0

# Un fold con muy pocas velas no produce una métrica interpretable.
MIN_WINDOW_BARS = 200

FOLDS_PATH = DATA_DIR / "multi_asset_walk_forward_folds.csv"
SUMMARY_PATH = DATA_DIR / "multi_asset_walk_forward_summary.csv"


def compound(returns_pct: pd.Series | list[float]) -> float:
    """Compone retornos porcentuales de ventanas contiguas."""
    total = 1.0
    for value in returns_pct:
        total *= 1 + float(value) / 100
    return (total - 1) * 100


def evaluate_window(
    signal_df: pd.DataFrame,
    *,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any] | None:
    """Corre el motor de backtest sobre un tramo temporal ya troceado."""
    window = signal_df.loc[start:end]

    if len(window) < MIN_WINDOW_BARS:
        return None

    trades_df, equity_df = run_position_backtest(
        window,
        symbol=symbol,
        cooldown_hours=COOLDOWN_HOURS,
        min_hold_hours=MIN_HOLD_HOURS,
    )

    # `window` es df_1h + columnas de señal, así que sirve como fuente del
    # benchmark: build_metrics solo lee la columna `close`.
    return build_metrics(df_1h=window, trades_df=trades_df, equity_curve_df=equity_df)


def evaluate_asset(
    symbol: str,
    *,
    refresh: bool,
    train_days: int,
    test_days: int,
    data_dir: Path = DATA_DIR,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    df_1h, df_4h = load_pair_data(symbol, refresh=refresh, data_dir=data_dir)

    # Señales una sola vez sobre el histórico completo; el troceado va después.
    signal_df = build_regime_signals(df_1h, df_4h, **CONFIG)

    windows = generate_walk_forward_windows(
        df_1h,
        train_days=train_days,
        test_days=test_days,
    )

    fold_rows: list[dict[str, Any]] = []

    for window in windows:
        metrics = evaluate_window(
            signal_df,
            symbol=symbol,
            start=window["test_start"],
            end=window["test_end"],
        )

        if metrics is None:
            continue

        fold_rows.append(
            {
                "symbol": symbol,
                "fold": window["fold"],
                "test_start": window["test_start"],
                "test_end": window["test_end"],
                **metrics,
            }
        )

    full_metrics = evaluate_window(
        signal_df,
        symbol=symbol,
        start=signal_df.index.min(),
        end=signal_df.index.max(),
    )

    summary = build_asset_summary(
        symbol=symbol,
        fold_rows=fold_rows,
        full_metrics=full_metrics,
        signal_df=signal_df,
    )

    return fold_rows, summary


def build_asset_summary(
    *,
    symbol: str,
    fold_rows: list[dict[str, Any]],
    full_metrics: dict[str, Any] | None,
    signal_df: pd.DataFrame,
) -> dict[str, Any]:
    folds_df = pd.DataFrame(fold_rows)

    summary: dict[str, Any] = {
        "symbol": symbol,
        "data_start": signal_df.index.min(),
        "data_end": signal_df.index.max(),
        "folds": len(folds_df),
        # Full period: la mirada que ya teníamos (run_multi_asset_eval).
        "full_return_pct": None if full_metrics is None else full_metrics["total_return_pct"],
        "full_benchmark_pct": None if full_metrics is None else full_metrics["benchmark_return_pct"],
        "full_max_drawdown_pct": None if full_metrics is None else full_metrics["max_drawdown_pct"],
        "full_benchmark_drawdown_pct": (
            None if full_metrics is None else full_metrics["benchmark_drawdown_pct"]
        ),
        "full_trades": None if full_metrics is None else full_metrics["total_trades"],
    }

    if folds_df.empty:
        return summary

    strategy_compounded = compound(folds_df["total_return_pct"])
    benchmark_compounded = compound(folds_df["benchmark_return_pct"])

    summary.update(
        {
            # Walk-forward: la mirada honesta (test contiguos, config fija).
            "wf_return_pct": strategy_compounded,
            "wf_benchmark_pct": benchmark_compounded,
            "wf_excess_pp": strategy_compounded - benchmark_compounded,
            "wf_avg_fold_return_pct": folds_df["total_return_pct"].mean(),
            "wf_median_fold_return_pct": folds_df["total_return_pct"].median(),
            "wf_worst_fold_return_pct": folds_df["total_return_pct"].min(),
            "wf_best_fold_return_pct": folds_df["total_return_pct"].max(),
            "wf_positive_folds": int((folds_df["total_return_pct"] > 0).sum()),
            "wf_beat_benchmark_folds": int(
                (folds_df["total_return_pct"] > folds_df["benchmark_return_pct"]).sum()
            ),
            "wf_avg_drawdown_pct": folds_df["max_drawdown_pct"].mean(),
            "wf_avg_benchmark_drawdown_pct": folds_df["benchmark_drawdown_pct"].mean(),
            "wf_total_trades": int(folds_df["total_trades"].sum()),
            "wf_avg_exposure_pct": folds_df["exposure_pct"].mean(),
        }
    )

    return summary


def print_report(folds_df: pd.DataFrame, summary_df: pd.DataFrame) -> None:
    pd.set_option("display.width", 220)

    print("\n===== FOLDS (test out-of-sample, config fija) =====\n")
    fold_columns = [
        "symbol",
        "fold",
        "test_start",
        "test_end",
        "total_return_pct",
        "benchmark_return_pct",
        "max_drawdown_pct",
        "benchmark_drawdown_pct",
        "total_trades",
        "exposure_pct",
    ]
    printable = folds_df[fold_columns].copy()
    printable["test_start"] = printable["test_start"].dt.strftime("%Y-%m-%d")
    printable["test_end"] = printable["test_end"].dt.strftime("%Y-%m-%d")
    print(printable.round(2).to_string(index=False))

    print("\n===== FULL PERIOD vs WALK-FORWARD (por activo) =====\n")
    comparison_columns = [
        "symbol",
        "folds",
        "full_return_pct",
        "full_benchmark_pct",
        "wf_return_pct",
        "wf_benchmark_pct",
        "wf_excess_pp",
        "wf_positive_folds",
        "wf_beat_benchmark_folds",
        "wf_avg_drawdown_pct",
        "wf_avg_benchmark_drawdown_pct",
        "wf_total_trades",
        "wf_avg_exposure_pct",
    ]
    available = [column for column in comparison_columns if column in summary_df.columns]
    print(summary_df[available].round(2).to_string(index=False))

    print("\n===== LECTURA =====\n")
    for _, row in summary_df.iterrows():
        if pd.isna(row.get("wf_return_pct")):
            print(f"{row['symbol']}: sin folds suficientes.")
            continue

        beat = row["wf_return_pct"] > row["wf_benchmark_pct"]
        defends = row["wf_avg_drawdown_pct"] < row["wf_avg_benchmark_drawdown_pct"]

        print(
            f"{row['symbol']}: walk-forward {row['wf_return_pct']:+.1f}% vs benchmark "
            f"{row['wf_benchmark_pct']:+.1f}% ({row['wf_excess_pp']:+.1f} pp) | "
            f"folds positivos {int(row['wf_positive_folds'])}/{int(row['folds'])} | "
            f"drawdown medio {row['wf_avg_drawdown_pct']:.1f}% vs "
            f"{row['wf_avg_benchmark_drawdown_pct']:.1f}% | "
            f"{'BATE' if beat else 'NO bate'} al benchmark, "
            f"{'defiende' if defends else 'NO defiende'}."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Walk-forward no-lookahead por activo con la config fija de BTC."
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-descarga OHLCV vía ccxt y sobreescribe los CSV cacheados.",
    )
    parser.add_argument("--assets", nargs="+", default=PAIRS, help="Pares a evaluar.")
    parser.add_argument("--train-days", type=int, default=270)
    parser.add_argument("--test-days", type=int, default=60)
    parser.add_argument(
        "--frozen",
        action="store_true",
        help="Lee data/frozen/ (dataset de la validación original) en vez de data/.",
    )
    args = parser.parse_args()

    if args.frozen and args.refresh:
        parser.error("--frozen y --refresh son incompatibles: el congelado no se refresca.")

    data_dir = FROZEN_DATA_DIR if args.frozen else DATA_DIR

    print("\n========== WALK-FORWARD MULTI-ACTIVO (no-lookahead) ==========")
    print(f"Config fija: {CONFIG} | cooldown={COOLDOWN_HOURS} min_hold={MIN_HOLD_HOURS}")
    print(f"Ventanas: train {args.train_days}d / test {args.test_days}d")
    print(f"Datos: {data_dir}")

    all_folds: list[dict[str, Any]] = []
    all_summaries: list[dict[str, Any]] = []

    for symbol in args.assets:
        print(f"\nEvaluando {symbol}...")
        fold_rows, summary = evaluate_asset(
            symbol,
            refresh=args.refresh,
            train_days=args.train_days,
            test_days=args.test_days,
            data_dir=data_dir,
        )
        print(f"  folds evaluados: {len(fold_rows)}")
        all_folds.extend(fold_rows)
        all_summaries.append(summary)

    folds_df = pd.DataFrame(all_folds)
    summary_df = pd.DataFrame(all_summaries)

    # El run sobre el congelado es un control; no debe pisar el resultado vigente.
    suffix = "_frozen" if args.frozen else ""
    folds_path = FOLDS_PATH.with_name(f"{FOLDS_PATH.stem}{suffix}.csv")
    summary_path = SUMMARY_PATH.with_name(f"{SUMMARY_PATH.stem}{suffix}.csv")

    folds_df.to_csv(folds_path, index=False)
    summary_df.to_csv(summary_path, index=False)

    print_report(folds_df, summary_df)

    print(f"\nFolds:   {folds_path}")
    print(f"Resumen: {summary_path}")


if __name__ == "__main__":
    main()
