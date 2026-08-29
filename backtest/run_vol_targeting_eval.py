"""
¿El vol-targeting convierte la reducción de drawdown en retorno? (research offline)

Compara la estrategia ACTUAL (100% dentro / 100% fuera) contra variantes que
dimensionan la posición por volatilidad, sobre los mismos datos y la misma señal
de régimen. La señal no cambia: el vol-targeting solo decide CUÁNTO, nunca CUÁNDO.

Se evalúa en dos regímenes de medida:
- full period: la mirada optimista.
- walk-forward (tests contiguos, config fija): la mirada honesta, la misma
  metodología que dejó al descubierto el espejismo del full-period el 2026-08-26.

AVISO SOBRE APALANCAMIENTO: las variantes con `max_leverage > 1` no modelan coste
de financiación, liquidaciones ni huecos de precio. Sus números son OPTIMISTAS.

Uso:
    python -m backtest.run_vol_targeting_eval
    python -m backtest.run_vol_targeting_eval --assets BTC/USDT ETH/USDT
"""

from __future__ import annotations

import argparse
import warnings
from typing import Any

import pandas as pd

from app.core.signals import build_regime_signals, compute_position_state
from backtest.common import DATA_DIR, generate_walk_forward_windows, load_pair_data
from backtest.run_multi_asset_walk_forward import CONFIG, compound
from backtest.vol_targeting import (
    compute_weights,
    realised_volatility,
    simulate_weighted_equity,
)

warnings.filterwarnings("ignore", category=FutureWarning)

PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]

VOL_WINDOW = 168  # 1 semana de velas 1h
FEE = 0.001

# La variante "baseline" reproduce la estrategia actual: peso 1 dentro, 0 fuera.
VARIANTS: list[dict[str, Any]] = [
    {"name": "baseline (100/0)", "target_vol": None},
    {"name": "vol 30% cap 1.0", "target_vol": 0.30, "max_leverage": 1.0},
    {"name": "vol 40% cap 1.0", "target_vol": 0.40, "max_leverage": 1.0},
    {"name": "vol 50% cap 1.0", "target_vol": 0.50, "max_leverage": 1.0},
    {"name": "vol 40% cap 1.5 (LEV)", "target_vol": 0.40, "max_leverage": 1.5},
    {"name": "vol 50% cap 2.0 (LEV)", "target_vol": 0.50, "max_leverage": 2.0},
]

RESULTS_PATH = DATA_DIR / "vol_targeting_eval.csv"
WF_PATH = DATA_DIR / "vol_targeting_walk_forward.csv"


def build_inputs(symbol: str) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Señal de régimen + estado de posición + volatilidad realizada."""
    df_1h, df_4h = load_pair_data(symbol)
    signal_df = build_regime_signals(df_1h, df_4h, **CONFIG)

    in_position = compute_position_state(
        signal_df,
        cooldown_hours=0,
        min_hold_hours=0,
    )
    volatility = realised_volatility(signal_df["close"], window=VOL_WINDOW)

    return signal_df, in_position, volatility


def evaluate_variant(
    signal_df: pd.DataFrame,
    in_position: pd.Series,
    volatility: pd.Series,
    variant: dict[str, Any],
) -> dict[str, Any]:
    if variant["target_vol"] is None:
        weights = in_position.astype(float)
    else:
        weights = compute_weights(
            in_position,
            volatility,
            target_vol=variant["target_vol"],
            max_leverage=variant["max_leverage"],
        )

    result = simulate_weighted_equity(signal_df["close"], weights, fee=FEE)

    close = signal_df["close"]
    benchmark_return = (float(close.iloc[-1]) / float(close.iloc[0]) - 1) * 100

    return {
        "variant": variant["name"],
        "total_return_pct": result.total_return_pct,
        "benchmark_return_pct": benchmark_return,
        "max_drawdown_pct": result.max_drawdown_pct,
        "annualised_vol_pct": result.annualised_vol_pct,
        "return_over_drawdown": result.return_over_drawdown,
        "avg_weight": result.avg_weight,
        "max_weight": result.max_weight,
        "turnover": result.turnover,
        "fees_paid_pct": result.fees_paid_pct,
    }


def evaluate_full_period(symbol: str) -> list[dict[str, Any]]:
    signal_df, in_position, volatility = build_inputs(symbol)

    rows = []
    for variant in VARIANTS:
        row = evaluate_variant(signal_df, in_position, volatility, variant)
        row["symbol"] = symbol
        rows.append(row)
    return rows


def evaluate_walk_forward(symbol: str) -> list[dict[str, Any]]:
    """Mismo troceado que el walk-forward multi-activo: solo tramos de test."""
    signal_df, in_position, volatility = build_inputs(symbol)
    windows = generate_walk_forward_windows(signal_df, train_days=270, test_days=60)

    rows: list[dict[str, Any]] = []

    for variant in VARIANTS:
        fold_returns: list[float] = []
        fold_benchmarks: list[float] = []
        drawdowns: list[float] = []

        for window in windows:
            start, end = window["test_start"], window["test_end"]
            sliced = signal_df.loc[start:end]

            if len(sliced) < 200:
                continue

            metrics = evaluate_variant(
                sliced,
                in_position.loc[start:end],
                volatility.loc[start:end],
                variant,
            )
            fold_returns.append(metrics["total_return_pct"])
            fold_benchmarks.append(metrics["benchmark_return_pct"])
            drawdowns.append(metrics["max_drawdown_pct"])

        if not fold_returns:
            continue

        wf_return = compound(fold_returns)
        wf_benchmark = compound(fold_benchmarks)

        rows.append(
            {
                "symbol": symbol,
                "variant": variant["name"],
                "folds": len(fold_returns),
                "wf_return_pct": wf_return,
                "wf_benchmark_pct": wf_benchmark,
                "wf_excess_pp": wf_return - wf_benchmark,
                "wf_avg_drawdown_pct": sum(drawdowns) / len(drawdowns),
                "wf_positive_folds": sum(1 for r in fold_returns if r > 0),
            }
        )

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Evalúa vol-targeting sobre el overlay.")
    parser.add_argument("--assets", nargs="+", default=PAIRS)
    args = parser.parse_args()

    pd.set_option("display.width", 220)

    full_rows: list[dict[str, Any]] = []
    wf_rows: list[dict[str, Any]] = []

    for symbol in args.assets:
        print(f"Evaluando {symbol}...")
        full_rows.extend(evaluate_full_period(symbol))
        wf_rows.extend(evaluate_walk_forward(symbol))

    full_df = pd.DataFrame(full_rows)
    wf_df = pd.DataFrame(wf_rows)

    full_df.to_csv(RESULTS_PATH, index=False)
    wf_df.to_csv(WF_PATH, index=False)

    columns = [
        "symbol",
        "variant",
        "total_return_pct",
        "benchmark_return_pct",
        "max_drawdown_pct",
        "annualised_vol_pct",
        "return_over_drawdown",
        "avg_weight",
        "turnover",
        "fees_paid_pct",
    ]
    print("\n===== FULL PERIOD =====\n")
    print(full_df[columns].round(2).to_string(index=False))

    print("\n===== WALK-FORWARD (tests contiguos) =====\n")
    print(wf_df.round(2).to_string(index=False))

    print("\n===== ¿MEJORA EL RETORNO POR UNIDAD DE DRAWDOWN? (full period) =====\n")
    for symbol in args.assets:
        subset = full_df[full_df["symbol"] == symbol]
        if subset.empty:
            continue
        base = subset[subset["variant"] == "baseline (100/0)"].iloc[0]
        best = subset.loc[subset["return_over_drawdown"].idxmax()]
        verdict = "MEJORA" if best["variant"] != "baseline (100/0)" else "NO mejora"
        print(
            f"{symbol}: baseline ret/dd {base['return_over_drawdown']:.2f} | "
            f"mejor '{best['variant']}' {best['return_over_drawdown']:.2f} -> {verdict}"
        )

    print(f"\nFull period: {RESULTS_PATH}")
    print(f"Walk-forward: {WF_PATH}")
    print(
        "\nAVISO: las variantes (LEV) usan apalancamiento y NO modelan coste de "
        "financiación, liquidaciones ni huecos. Sus cifras son optimistas."
    )


if __name__ == "__main__":
    main()
