"""
Vol-targeting sobre el overlay de régimen (research offline).

IDEA
----
El walk-forward del 2026-08-26 mostró que la estrategia recorta el drawdown ~a la
mitad del buy & hold en los 5 activos, pero no bate su retorno. Si el riesgo es la
mitad, se puede asumir MÁS exposición para el mismo riesgo: en vez de estar 100%
dentro o 100% fuera, se dimensiona la posición para apuntar a una volatilidad
objetivo.

    peso = vol_objetivo / vol_realizada   (acotado por `max_leverage`)

Esto NO crea edge: redistribuye riesgo. Sube la exposición cuando el mercado está
tranquilo y la baja cuando se agita. Puede mejorar el retorno ajustado a riesgo;
no convierte una estrategia perdedora en ganadora.

HONESTIDAD DEL MODELO
---------------------
- Sin lookahead: la volatilidad en `t` usa solo retornos cerrados hasta `t`, y el
  peso resultante se aplica al retorno de `t -> t+1`.
- Se cobran fees sobre el TURNOVER (|Δpeso|), no solo al entrar y salir. Es lo que
  suele matar al vol-targeting ingenuo: rebalancear cada vela sangra comisiones.
  Por eso hay una banda de rebalanceo.
- `max_leverage > 1` implica APALANCAMIENTO. El modelo NO cobra coste de
  financiación, ni modela liquidaciones, ni huecos de precio. Los resultados con
  apalancamiento son por tanto OPTIMISTAS y no deben leerse como alcanzables.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

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


def compute_weights(
    in_position: pd.Series,
    volatility: pd.Series,
    *,
    target_vol: float = 0.40,
    max_leverage: float = 1.0,
    rebalance_band: float = 0.10,
) -> pd.Series:
    """
    Peso de la cartera en cada vela.

    Fuera de posición el peso es 0 (la decisión de régimen manda: el vol-targeting
    solo dimensiona, nunca decide entrar o salir).

    `rebalance_band` evita rebalancear por ruido: el peso solo se mueve si el
    objetivo se aleja más de esa fracción del peso actual. Sin banda, el turnover
    (y las comisiones) se disparan.
    """
    target = (target_vol / volatility).clip(upper=max_leverage)
    target = target.where(volatility.notna(), 0.0).fillna(0.0)
    target = target.where(in_position.astype(bool), 0.0)

    weights: list[float] = []
    current = 0.0

    for value in target:
        desired = float(value)

        if desired == 0.0 or current == 0.0:
            # Entrar o salir siempre se ejecuta: es la señal, no un ajuste.
            current = desired
        elif abs(desired - current) > rebalance_band * current:
            current = desired

        weights.append(current)

    return pd.Series(weights, index=in_position.index, name="weight")


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
