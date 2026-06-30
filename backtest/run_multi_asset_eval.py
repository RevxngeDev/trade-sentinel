"""
Evaluación offline (research): aplica la CONFIG FIJA validada para BTC/USDT
(entry=2, exit=2, exit_buffer=0.02, cooldown=0, min_hold=0) a varios activos,
para ver si el régimen defensivo GENERALIZA o si cada par necesita su propia
validación. No toca el paper trading en vivo; usa datos históricos (Binance).

Uso: python -m backtest.run_multi_asset_eval
"""

from __future__ import annotations

import warnings

import pandas as pd

from app.core.signals import build_regime_signals
from backtest.common import DATA_DIR, load_pair_data
from backtest.engine import build_metrics, run_position_backtest

warnings.filterwarnings("ignore", category=FutureWarning)

PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]

CONFIG = dict(
    entry_confirmation_bars=2,
    exit_confirmation_bars=2,
    exit_buffer_pct=0.02,
)
COOLDOWN_HOURS = 0
MIN_HOLD_HOURS = 0

RESULTS_PATH = DATA_DIR / "multi_asset_eval.csv"


def evaluate(symbol: str) -> dict:
    df_1h, df_4h = load_pair_data(symbol)
    signal_df = build_regime_signals(df_1h, df_4h, **CONFIG)
    trades_df, equity_df = run_position_backtest(
        signal_df,
        symbol=symbol,
        cooldown_hours=COOLDOWN_HOURS,
        min_hold_hours=MIN_HOLD_HOURS,
    )
    metrics = build_metrics(df_1h=df_1h, trades_df=trades_df, equity_curve_df=equity_df)
    metrics["symbol"] = symbol
    return metrics


def main() -> None:
    rows = []
    for symbol in PAIRS:
        print(f"Evaluando {symbol}...")
        rows.append(evaluate(symbol))

    df = pd.DataFrame(rows)
    columns = [
        "symbol",
        "total_return_pct",
        "benchmark_return_pct",
        "max_drawdown_pct",
        "benchmark_drawdown_pct",
        "profit_factor",
        "total_trades",
        "win_rate_pct",
        "exposure_pct",
        "beat_benchmark",
    ]

    df[columns].to_csv(RESULTS_PATH, index=False)

    pd.set_option("display.width", 200)
    print("\n===== Config fija entry=2/exit=2/buffer=0.02 en multi-activo (full period) =====")
    print(df[columns].round(2).to_string(index=False))
    print(f"\nGuardado en {RESULTS_PATH}")


if __name__ == "__main__":
    main()
