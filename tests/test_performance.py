from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.performance import compute_equity


def _sig(hours: int, action: str, price: float):
    return SimpleNamespace(
        action=action,
        price=price,
        signal_timestamp=datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(hours=hours),
    )


def test_empty_or_single_signal_returns_zero() -> None:
    assert compute_equity([]).strategy_return_pct == 0.0
    assert compute_equity([_sig(0, "CASH", 100)]).round_trips == 0


def test_one_round_trip_gain() -> None:
    # CASH -> BUY@100 -> HOLD@110 -> CASH@120. En posición durante 2 de 3 intervalos.
    signals = [
        _sig(0, "CASH", 100),
        _sig(4, "BUY", 100),
        _sig(8, "HOLD", 110),
        _sig(12, "CASH", 120),
    ]
    result = compute_equity(signals, fee=0.001)

    assert result.round_trips == 1
    assert result.exposure_pct == pytest.approx(66.67, abs=0.01)
    assert result.benchmark_return_pct == pytest.approx(20.0, abs=0.001)
    # 0.999 (fee entrada) * 1.20 (subida) * 0.999 (fee salida) - 1
    assert result.strategy_return_pct == pytest.approx(19.76, abs=0.01)
    assert len(result.series) == 4


def test_cash_only_has_no_exposure() -> None:
    signals = [_sig(0, "CASH", 100), _sig(4, "CASH", 90), _sig(8, "CASH", 95)]
    result = compute_equity(signals)

    assert result.round_trips == 0
    assert result.exposure_pct == 0.0
    assert result.strategy_return_pct == 0.0  # nunca en posición
    assert result.benchmark_return_pct == pytest.approx(-5.0, abs=0.001)
