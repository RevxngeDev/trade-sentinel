"""
Métricas de performance — fuente única de verdad.

Antes estaban duplicadas verbatim en los scripts de backtest de régimen.
"""

from __future__ import annotations

import pandas as pd


def calculate_benchmark_return(close: pd.Series) -> float:
    first = close.iloc[0]
    last = close.iloc[-1]
    return ((last / first) - 1) * 100


def calculate_drawdown(equity: pd.Series) -> float:
    running_max = equity.cummax()
    drawdown = (equity / running_max) - 1
    return abs(drawdown.min() * 100)


def calculate_profit_factor(trades_df: pd.DataFrame) -> float | None:
    if trades_df.empty:
        return None

    gross_profit = trades_df.loc[trades_df["net_pnl_cash"] > 0, "net_pnl_cash"].sum()
    gross_loss = abs(
        trades_df.loc[trades_df["net_pnl_cash"] < 0, "net_pnl_cash"].sum()
    )

    if gross_loss == 0:
        return None

    return gross_profit / gross_loss


def format_timedelta(delta: pd.Timedelta) -> str:
    total_hours = int(delta.total_seconds() // 3600)
    days = total_hours // 24
    hours = total_hours % 24
    return f"{days}d {hours}h"
