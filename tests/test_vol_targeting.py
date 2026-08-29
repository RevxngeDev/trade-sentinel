"""
Tests del vol-targeting.

Lo que protegen: que no haya lookahead, que el peso nunca decida entrar o salir
(eso lo manda la señal de régimen), y que las comisiones de rebalanceo se cobren
de verdad — es justo lo que suele desmontar al vol-targeting ingenuo.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.vol_targeting import (
    compute_weights,
    realised_volatility,
    simulate_weighted_equity,
)


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")


# ============================================================
# Volatilidad
# ============================================================


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


def test_higher_volatility_lowers_the_weight() -> None:
    calm = pd.Series(0.20, index=_index(10))
    wild = pd.Series(0.80, index=_index(10))
    in_position = pd.Series(True, index=_index(10))

    calm_weights = compute_weights(in_position, calm, target_vol=0.40, max_leverage=5.0)
    wild_weights = compute_weights(in_position, wild, target_vol=0.40, max_leverage=5.0)

    assert calm_weights.iloc[-1] > wild_weights.iloc[-1]


# ============================================================
# Pesos
# ============================================================


def test_weight_is_zero_when_out_of_position() -> None:
    """El vol-targeting dimensiona; NUNCA decide entrar o salir."""
    index = _index(10)
    in_position = pd.Series([True] * 5 + [False] * 5, index=index)
    vol = pd.Series(0.20, index=index)

    weights = compute_weights(in_position, vol, target_vol=0.40, max_leverage=1.0)

    assert (weights.iloc[5:] == 0.0).all()
    assert (weights.iloc[:5] > 0).all()


def test_weight_respects_the_leverage_cap() -> None:
    index = _index(10)
    in_position = pd.Series(True, index=index)
    very_calm = pd.Series(0.01, index=index)  # pediría un peso enorme

    weights = compute_weights(in_position, very_calm, target_vol=0.40, max_leverage=1.0)

    assert weights.max() == pytest.approx(1.0)


def test_missing_volatility_yields_zero_weight() -> None:
    """Sin volatilidad calculable no se dimensiona a ciegas."""
    index = _index(5)
    in_position = pd.Series(True, index=index)
    vol = pd.Series([np.nan] * 5, index=index)

    weights = compute_weights(in_position, vol, target_vol=0.40)

    assert (weights == 0.0).all()


def test_rebalance_band_suppresses_small_adjustments() -> None:
    index = _index(4)
    in_position = pd.Series(True, index=index)
    # Volatilidad que se mueve poco: el peso objetivo apenas cambia.
    vol = pd.Series([0.40, 0.41, 0.40, 0.41], index=index)

    banded = compute_weights(
        in_position, vol, target_vol=0.40, max_leverage=1.0, rebalance_band=0.50
    )
    unbanded = compute_weights(
        in_position, vol, target_vol=0.40, max_leverage=1.0, rebalance_band=0.0
    )

    assert banded.nunique() < unbanded.nunique()


# ============================================================
# Simulación
# ============================================================


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
