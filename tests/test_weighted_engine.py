"""
Tests de la simulación de carteras con peso variable (en `backtest.engine`).

Vienen del estudio de vol-targeting, que se descartó; las funciones se
quedaron porque son infraestructura: cualquier estrategia futura que no sea
binaria dentro/fuera las necesita. Protegen que no haya lookahead y que las
comisiones de rebalanceo se cobren de verdad.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.engine import realised_volatility, simulate_weighted_equity


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")


def test_volatility_is_nan_until_the_window_is_full() -> None:
    """Sin historia suficiente no se inventa una volatilidad."""
    close = pd.Series(np.linspace(100, 110, 50), index=_index(50))

    vol = realised_volatility(close, window=24)

    assert vol.iloc[:24].isna().all()
    assert vol.iloc[30:].notna().all()


def test_volatility_uses_only_past_returns() -> None:
    """
    No-lookahead: cambiar un precio FUTURO no puede alterar la volatilidad de hoy.
    """
    close = pd.Series(np.linspace(100, 200, 120), index=_index(120))
    vol_before = realised_volatility(close, window=24)

    tampered = close.copy()
    tampered.iloc[100:] *= 3  # sacudida sólo en el futuro
    vol_after = realised_volatility(tampered, window=24)

    pd.testing.assert_series_equal(vol_before.iloc[:100], vol_after.iloc[:100])


def test_full_weight_tracks_the_asset() -> None:
    index = _index(3)
    close = pd.Series([100.0, 110.0, 121.0], index=index)
    weights = pd.Series([1.0, 1.0, 1.0], index=index)

    result = simulate_weighted_equity(close, weights, fee=0.0)

    assert result.total_return_pct == pytest.approx(21.0)


def test_half_weight_halves_the_move() -> None:
    index = _index(2)
    close = pd.Series([100.0, 120.0], index=index)
    weights = pd.Series([0.5, 0.5], index=index)

    result = simulate_weighted_equity(close, weights, fee=0.0)

    assert result.total_return_pct == pytest.approx(10.0)


def test_zero_weight_is_immune_to_price(_=None) -> None:
    index = _index(3)
    close = pd.Series([100.0, 50.0, 25.0], index=index)
    weights = pd.Series([0.0, 0.0, 0.0], index=index)

    result = simulate_weighted_equity(close, weights, fee=0.001)

    assert result.total_return_pct == pytest.approx(0.0)
    assert result.fees_paid_pct == pytest.approx(0.0)


def test_rebalancing_costs_are_charged_on_turnover() -> None:
    """
    El punto que hunde al vol-targeting ingenuo: mover el peso cuesta dinero
    aunque el precio no se mueva.
    """
    index = _index(5)
    close = pd.Series([100.0] * 5, index=index)
    churn = pd.Series([1.0, 0.2, 1.0, 0.2, 1.0], index=index)

    result = simulate_weighted_equity(close, churn, fee=0.01)

    assert result.total_return_pct < 0
    # 1.0 al abrir desde plano + 4 saltos de 0.8 entre 1.0 y 0.2.
    assert result.turnover == pytest.approx(1.0 + 0.8 * 4)
    assert result.fees_paid_pct > 0


def test_no_lookahead_last_weight_cannot_act() -> None:
    """
    El peso de la última vela no tiene retorno futuro al que aplicarse: si
    influyera, sería lookahead.
    """
    index = _index(3)
    close = pd.Series([100.0, 110.0, 120.0], index=index)

    ending_flat = pd.Series([1.0, 1.0, 0.0], index=index)
    ending_full = pd.Series([1.0, 1.0, 1.0], index=index)

    flat = simulate_weighted_equity(close, ending_flat, fee=0.0)
    full = simulate_weighted_equity(close, ending_full, fee=0.0)

    assert flat.total_return_pct == pytest.approx(full.total_return_pct)


def test_drawdown_is_reported() -> None:
    index = _index(4)
    close = pd.Series([100.0, 120.0, 60.0, 90.0], index=index)
    weights = pd.Series([1.0, 1.0, 1.0, 1.0], index=index)

    result = simulate_weighted_equity(close, weights, fee=0.0)

    assert result.max_drawdown_pct == pytest.approx(50.0, abs=0.5)
