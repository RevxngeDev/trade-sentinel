"""
Reconstrucción de la equity real de la estrategia a partir de las señales
guardadas (BUY/HOLD = en posición, CASH = fuera), con fees. Es el número
honesto del paper trading (a diferencia del tracker per-señal, que solapa
ventanas de 4h y no representa el retorno real).

Función pura: recibe cualquier objeto con `.action`, `.price`,
`.signal_timestamp`, para no acoplarla a los schemas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EquityPoint:
    timestamp: datetime
    strategy: float   # equity normalizada (inicio = 1.0)
    benchmark: float  # buy & hold normalizado (inicio = 1.0)


@dataclass
class PerformanceResult:
    strategy_return_pct: float = 0.0
    benchmark_return_pct: float = 0.0
    difference_pp: float = 0.0
    exposure_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    round_trips: int = 0
    initial_equity: float = 1000.0
    final_strategy_equity: float = 1000.0
    series: list[EquityPoint] = field(default_factory=list)


def compute_equity(
    signals: list,
    *,
    fee: float = 0.001,
    initial_equity: float = 1000.0,
) -> PerformanceResult:
    ordered = sorted(signals, key=lambda s: s.signal_timestamp)
    if len(ordered) < 2:
        return PerformanceResult(
            initial_equity=initial_equity,
            final_strategy_equity=initial_equity,
        )

    first_price = float(ordered[0].price)
    strat = 1.0
    prev_in = False
    round_trips = 0
    in_intervals = 0
    peak = 1.0
    max_dd = 0.0
    series: list[EquityPoint] = []

    for i, signal in enumerate(ordered):
        in_position = signal.action != "CASH"

        if in_position != prev_in:
            strat *= 1 - fee  # fee al entrar o al salir
            if in_position:
                round_trips += 1

        series.append(
            EquityPoint(
                timestamp=signal.signal_timestamp,
                strategy=strat,
                benchmark=float(signal.price) / first_price,
            )
        )

        if in_position and i < len(ordered) - 1:
            strat *= float(ordered[i + 1].price) / float(signal.price)
            in_intervals += 1

        peak = max(peak, strat)
        max_dd = max(max_dd, (peak - strat) / peak)
        prev_in = in_position

    strategy_return = (strat - 1) * 100
    benchmark_return = (series[-1].benchmark - 1) * 100

    return PerformanceResult(
        strategy_return_pct=round(strategy_return, 4),
        benchmark_return_pct=round(benchmark_return, 4),
        difference_pp=round(strategy_return - benchmark_return, 4),
        exposure_pct=round(in_intervals / (len(ordered) - 1) * 100, 2),
        max_drawdown_pct=round(max_dd * 100, 2),
        round_trips=round_trips,
        initial_equity=initial_equity,
        final_strategy_equity=round(initial_equity * strat, 2),
        series=series,
    )
