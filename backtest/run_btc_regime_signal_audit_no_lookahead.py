from __future__ import annotations

import warnings
from typing import Any

import pandas as pd

from app.core.regime import add_regime_conditions
from app.core.signals import build_regime_signals
from backtest.common import DATA_DIR, FEES, load_pair_data
from backtest.engine import build_metrics, run_position_backtest


warnings.filterwarnings("ignore", category=FutureWarning)

SYMBOL = "BTC/USDT"

TRADES_PATH = DATA_DIR / "btc_regime_no_lookahead_trades.csv"
SUMMARY_PATH = DATA_DIR / "btc_regime_no_lookahead_summary.csv"
EQUITY_CURVE_PATH = DATA_DIR / "btc_regime_no_lookahead_equity_curve.csv"
CURRENT_STATUS_PATH = DATA_DIR / "btc_regime_no_lookahead_current_status.csv"


# ============================================================
# Resumen y estado actual (específicos del audit)
# ============================================================

def build_summary(
    df_1h: pd.DataFrame,
    trades_df: pd.DataFrame,
    equity_curve_df: pd.DataFrame,
) -> pd.DataFrame:
    metrics = build_metrics(df_1h=df_1h, trades_df=trades_df, equity_curve_df=equity_curve_df)

    summary = {
        "symbol": SYMBOL,
        "strategy_name": "btc_regime_allocation_super_strict_bullish_no_lookahead",
        "lookahead_fix": "uses previous closed 4h regime with shift(1)",
        "fees_rate": FEES,
        **metrics,
        "entry_logic": (
            "previous closed 4h candle: close > ema50, close > ema200, "
            "ema50 > ema200, ema50 rising, ema200 rising, rsi_14 > 50"
        ),
        "exit_logic": "exit when previous closed 4h super_strict_bullish regime turns off",
    }

    return pd.DataFrame([summary])


def build_current_status(df_4h: pd.DataFrame, signal_df: pd.DataFrame) -> pd.DataFrame:
    regime_4h = add_regime_conditions(df_4h)

    last_1h = signal_df.iloc[-1]
    last_4h = regime_4h.iloc[-1]

    # Última vela 4h usada realmente para decisión (la anterior a la última).
    decision_ts_4h = regime_4h.index[-2] if len(regime_4h) >= 2 else regime_4h.index[-1]
    decision_row_4h = regime_4h.loc[decision_ts_4h]

    regime_on = bool(last_1h["decision_regime_on"])
    action = "HOLD_BTC_OR_BUY_IF_NOT_IN_POSITION" if regime_on else "CASH_OR_SELL_IF_IN_POSITION"

    status = {
        "symbol": SYMBOL,
        "timestamp_1h": signal_df.index[-1],
        "latest_4h_timestamp_in_dataset": regime_4h.index[-1],
        "decision_4h_timestamp_used": decision_ts_4h,
        "last_close_1h": float(last_1h["close"]),
        "decision_close_4h_used": float(decision_row_4h["close"]),
        "regime_on_no_lookahead": regime_on,
        "entry_ready_now": bool(last_1h["entry_ready"]),
        "exit_ready_now": bool(last_1h["exit_ready"]),
        "recommended_action": action,
        "condition_close_above_ema50": bool(decision_row_4h["condition_close_above_ema50"]),
        "condition_close_above_ema200": bool(decision_row_4h["condition_close_above_ema200"]),
        "condition_ema50_above_ema200": bool(decision_row_4h["condition_ema50_above_ema200"]),
        "condition_ema50_rising": bool(decision_row_4h["condition_ema50_rising"]),
        "condition_ema200_rising": bool(decision_row_4h["condition_ema200_rising"]),
        "condition_rsi_above_50": bool(decision_row_4h["condition_rsi_above_50"]),
        "rsi_14_4h_used": float(decision_row_4h["rsi_14"]),
        "ema_50_4h_used": float(decision_row_4h["ema_50"]),
        "ema_200_4h_used": float(decision_row_4h["ema_200"]),
        "raw_regime_latest_4h": bool(last_4h["raw_regime_on"]),
    }

    return pd.DataFrame([status])


# ============================================================
# Main
# ============================================================

def run_btc_regime_signal_audit_no_lookahead() -> None:
    print("\n========== BTC REGIME SIGNAL AUDIT - NO LOOKAHEAD ==========\n")

    print(f"Cargando datos para {SYMBOL}...")
    df_1h, df_4h = load_pair_data(SYMBOL)

    print(f"Velas 1h: {len(df_1h)} | 4h: {len(df_4h)}")
    print(f"Rango: {df_1h.index.min()} -> {df_1h.index.max()}")

    required = {"close", "ema_50", "ema_200", "rsi_14"}
    for name, frame in (("1h", df_1h), ("4h", df_4h)):
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"Faltan columnas en df_{name}: {missing}")

    # Audit base: régimen sin confirmation bars ni buffer (caso bars=1).
    signal_df = build_regime_signals(df_1h=df_1h, df_4h=df_4h)
    trades_df, equity_curve_df = run_position_backtest(signal_df, symbol=SYMBOL)

    summary_df = build_summary(df_1h=df_1h, trades_df=trades_df, equity_curve_df=equity_curve_df)
    current_status_df = build_current_status(df_4h=df_4h, signal_df=signal_df)

    trades_df.to_csv(TRADES_PATH, index=False)
    summary_df.to_csv(SUMMARY_PATH, index=False)
    equity_curve_df.to_csv(EQUITY_CURVE_PATH)
    current_status_df.to_csv(CURRENT_STATUS_PATH, index=False)

    print("\n========== SUMMARY NO LOOKAHEAD ==========\n")
    print(summary_df.to_string(index=False))

    print("\n========== CURRENT STATUS NO LOOKAHEAD ==========\n")
    print(current_status_df.to_string(index=False))

    print(f"\nResumen: {SUMMARY_PATH}")
    print(f"Trades: {TRADES_PATH}")


if __name__ == "__main__":
    run_btc_regime_signal_audit_no_lookahead()
