"""
Motor de backtest stateful (una sola implementación).

Reemplaza los dos loops casi idénticos que estaban en los scripts de régimen
(`run_manual_signal_audit` y `run_manual_v2_backtest`). El audit es el caso
particular cooldown=0 / min_hold=0.

Reglas:
- Entrada: si está flat, `entry_ready` y cooldown cumplido. Full allocation.
- Salida: si está en posición, `exit_ready` y min_hold cumplido.
- Fees: se cobra al entrar y al salir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.core.metrics import (
    calculate_benchmark_return,
    calculate_drawdown,
    calculate_profit_factor,
    format_timedelta,
)
from app.core.signals import compute_position_state
from backtest.common import FEES, INITIAL_CASH


def _record_trade(
    *,
    symbol: str,
    entry_time: pd.Timestamp,
    exit_time: pd.Timestamp,
    entry_price: float,
    exit_price: float,
    entry_equity_before: float,
    entry_fee_cash: float,
    units: float,
    exit_reason: str,
) -> dict[str, Any]:
    gross_exit_cash = units * exit_price
    exit_fee_cash = gross_exit_cash * FEES
    exit_cash_after_fee = gross_exit_cash - exit_fee_cash

    gross_price_return_pct = ((exit_price / entry_price) - 1) * 100
    net_trade_return_pct = ((exit_cash_after_fee / entry_equity_before) - 1) * 100
    net_pnl_cash = exit_cash_after_fee - entry_equity_before

    return {
        "symbol": symbol,
        "entry_time": entry_time,
        "exit_time": exit_time,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "duration": format_timedelta(exit_time - entry_time),
        "duration_hours": int((exit_time - entry_time).total_seconds() // 3600),
        "entry_equity_before": entry_equity_before,
        "exit_equity_after": exit_cash_after_fee,
        "gross_price_return_pct": gross_price_return_pct,
        "net_trade_return_pct": net_trade_return_pct,
        "net_pnl_cash": net_pnl_cash,
        "entry_fee_cash": entry_fee_cash,
        "exit_fee_cash": exit_fee_cash,
        "total_fee_cash": entry_fee_cash + exit_fee_cash,
        "exit_reason": exit_reason,
        "result": "win" if net_pnl_cash > 0 else "loss",
    }


def run_position_backtest(
    signal_df: pd.DataFrame,
    *,
    symbol: str = "BTC/USDT",
    cooldown_hours: int = 0,
    min_hold_hours: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    # La máquina de estado (compartida con el servicio en vivo) decide CUÁNDO
    # entrar/salir; aquí solo hacemos la contabilidad de capital y los trades.
    positions = compute_position_state(
        signal_df,
        cooldown_hours=cooldown_hours,
        min_hold_hours=min_hold_hours,
    )
    previous = positions.shift(1, fill_value=False)
    entered = positions & ~previous
    exited = (~positions) & previous

    cash = float(INITIAL_CASH)
    units = 0.0
    in_position = False

    entry_time: pd.Timestamp | None = None
    entry_price: float | None = None
    entry_equity_before: float | None = None
    entry_fee_cash: float | None = None

    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []

    for timestamp, row in signal_df.iterrows():
        close_price = float(row["close"])

        if bool(entered.loc[timestamp]):
            entry_time = timestamp
            entry_price = close_price
            entry_equity_before = cash
            entry_fee_cash = cash * FEES

            units = (cash * (1 - FEES)) / close_price
            cash = 0.0
            in_position = True

        elif bool(exited.loc[timestamp]):
            assert entry_time is not None
            trades.append(
                _record_trade(
                    symbol=symbol,
                    entry_time=entry_time,
                    exit_time=timestamp,
                    entry_price=float(entry_price),
                    exit_price=close_price,
                    entry_equity_before=float(entry_equity_before),
                    entry_fee_cash=float(entry_fee_cash),
                    units=units,
                    exit_reason="confirmed_regime_off",
                )
            )

            cash = trades[-1]["exit_equity_after"]
            units = 0.0
            in_position = False
            entry_time = entry_price = entry_equity_before = entry_fee_cash = None

        equity = units * close_price * (1 - FEES) if in_position else cash

        equity_curve.append(
            {
                "timestamp": timestamp,
                "close": close_price,
                "equity": equity,
                "in_position": in_position,
                "decision_regime_on": bool(row.get("decision_regime_on", False)),
                "entry_ready": bool(row["entry_ready"]),
                "exit_ready": bool(row["exit_ready"]),
            }
        )

    # Cierre virtual al final del dataset para la auditoría.
    if in_position:
        assert entry_time is not None
        last_timestamp = signal_df.index[-1]
        last_price = float(signal_df["close"].iloc[-1])

        trades.append(
            _record_trade(
                symbol=symbol,
                entry_time=entry_time,
                exit_time=last_timestamp,
                entry_price=float(entry_price),
                exit_price=last_price,
                entry_equity_before=float(entry_equity_before),
                entry_fee_cash=float(entry_fee_cash),
                units=units,
                exit_reason="open_position_closed_at_dataset_end",
            )
        )

        cash = trades[-1]["exit_equity_after"]
        units = 0.0
        in_position = False

        if equity_curve:
            equity_curve[-1]["equity"] = cash
            equity_curve[-1]["in_position"] = False

    trades_df = pd.DataFrame(trades)
    equity_curve_df = pd.DataFrame(equity_curve)

    if not equity_curve_df.empty:
        equity_curve_df["timestamp"] = pd.to_datetime(equity_curve_df["timestamp"])
        equity_curve_df = equity_curve_df.set_index("timestamp")

    return trades_df, equity_curve_df


def build_metrics(
    df_1h: pd.DataFrame,
    trades_df: pd.DataFrame,
    equity_curve_df: pd.DataFrame,
) -> dict[str, Any]:
    initial_equity = float(INITIAL_CASH)
    final_equity = float(equity_curve_df["equity"].iloc[-1])

    total_return_pct = ((final_equity / initial_equity) - 1) * 100
    benchmark_return_pct = calculate_benchmark_return(df_1h["close"])
    max_drawdown_pct = calculate_drawdown(equity_curve_df["equity"])

    benchmark_equity = (df_1h["close"] / df_1h["close"].iloc[0]) * INITIAL_CASH
    benchmark_drawdown_pct = calculate_drawdown(benchmark_equity)

    total_trades = len(trades_df)

    if total_trades > 0:
        wins = int((trades_df["net_pnl_cash"] > 0).sum())
        losses = int((trades_df["net_pnl_cash"] <= 0).sum())
        win_rate_pct = (wins / total_trades) * 100
        avg_trade_return_pct = trades_df["net_trade_return_pct"].mean()
        best_trade_pct = trades_df["net_trade_return_pct"].max()
        worst_trade_pct = trades_df["net_trade_return_pct"].min()
        avg_duration_hours = trades_df["duration_hours"].mean()
        total_fees_paid = trades_df["total_fee_cash"].sum()
        profit_factor = calculate_profit_factor(trades_df)
    else:
        wins = losses = 0
        win_rate_pct = avg_trade_return_pct = None
        best_trade_pct = worst_trade_pct = avg_duration_hours = None
        total_fees_paid = 0.0
        profit_factor = None

    exposure_pct = (
        equity_curve_df["in_position"].mean() * 100
        if not equity_curve_df.empty
        else None
    )

    return {
        "initial_equity": initial_equity,
        "final_equity": final_equity,
        "total_return_pct": total_return_pct,
        "benchmark_return_pct": benchmark_return_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "benchmark_drawdown_pct": benchmark_drawdown_pct,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate_pct,
        "profit_factor": profit_factor,
        "avg_trade_return_pct": avg_trade_return_pct,
        "best_trade_pct": best_trade_pct,
        "worst_trade_pct": worst_trade_pct,
        "avg_duration_hours": avg_duration_hours,
        "total_fees_paid": total_fees_paid,
        "exposure_pct": exposure_pct,
        "profitable": total_return_pct > 0,
        "beat_benchmark": total_return_pct > benchmark_return_pct,
    }


# ============================================================
# Carteras con peso VARIABLE
#
# El motor de arriba es binario: dentro o fuera. Estas funciones simulan un
# peso continuo y cobran comisión sobre el TURNOVER (|Δpeso|), no solo al
# entrar y salir. Es lo que hunde a las estrategias que rebalancean mucho, y
# omitirlo las hace parecer rentables cuando no lo son.
# ============================================================

# Velas de 1h: 24 * 365.
HOURLY_PERIODS_PER_YEAR = 24 * 365


def realised_volatility(
    close: pd.Series,
    *,
    window: int = 168,
    periods_per_year: int = HOURLY_PERIODS_PER_YEAR,
) -> pd.Series:
    """
    Volatilidad anualizada de los últimos `window` retornos CERRADOS.

    Causal por construcción: el valor en `t` solo usa retornos hasta `t`. Se deja
    así (sin shift extra) porque el retorno de `t` ya ocurrió cuando se decide el
    peso que se aplicará de `t` a `t+1`.
    """
    returns = close.pct_change()
    return returns.rolling(window, min_periods=window).std() * np.sqrt(periods_per_year)



@dataclass
class WeightedResult:
    total_return_pct: float
    max_drawdown_pct: float
    annualised_vol_pct: float
    return_over_drawdown: float
    turnover: float
    fees_paid_pct: float
    avg_weight: float
    max_weight: float
    equity: pd.Series



def simulate_weighted_equity(
    close: pd.Series,
    weights: pd.Series,
    *,
    fee: float = 0.001,
    periods_per_year: int = HOURLY_PERIODS_PER_YEAR,
) -> WeightedResult:
    """
    Equity de una cartera con peso variable, cobrando fee sobre el turnover.

    El peso en `t` se aplica al retorno de `t -> t+1` (sin lookahead).
    """
    prices = close.to_numpy(dtype=float)
    w = weights.to_numpy(dtype=float)

    equity = 1.0
    previous_weight = 0.0
    total_turnover = 0.0
    total_fees = 0.0

    curve = np.empty(len(prices))

    for i in range(len(prices)):
        turnover = abs(w[i] - previous_weight)
        fee_cost = equity * fee * turnover
        equity -= fee_cost

        total_turnover += turnover
        total_fees += fee_cost

        curve[i] = equity

        if i < len(prices) - 1:
            period_return = prices[i + 1] / prices[i] - 1
            equity *= 1 + w[i] * period_return

        previous_weight = w[i]

    equity_series = pd.Series(curve, index=weights.index, name="equity")

    running_peak = np.maximum.accumulate(curve)
    max_drawdown = float(np.max((running_peak - curve) / running_peak)) * 100

    equity_returns = pd.Series(curve).pct_change().dropna()
    annualised_vol = (
        float(equity_returns.std() * np.sqrt(periods_per_year)) * 100
        if len(equity_returns) > 1
        else 0.0
    )

    total_return = (equity - 1) * 100

    return WeightedResult(
        total_return_pct=total_return,
        max_drawdown_pct=max_drawdown,
        annualised_vol_pct=annualised_vol,
        # Retorno por unidad de dolor: el número que el vol-targeting pretende mejorar.
        return_over_drawdown=total_return / max_drawdown if max_drawdown > 0 else 0.0,
        turnover=total_turnover,
        fees_paid_pct=total_fees * 100,
        avg_weight=float(np.mean(w)),
        max_weight=float(np.max(w)) if len(w) else 0.0,
        equity=equity_series,
    )
