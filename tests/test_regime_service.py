from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.config import settings
from app.core.indicators import add_core_indicators
from app.core.signals import build_regime_signals, compute_position_state
from app.schemas.regime import RegimeResponse
from app.services.regime_service import RegimeService


DATA_DIR = Path("data")


def _load(timeframe: str) -> pd.DataFrame:
    path = DATA_DIR / f"BTC_USDT_{timeframe}.csv"
    if not path.exists():
        pytest.skip(f"Falta el dataset {path}")
    return pd.read_csv(path, parse_dates=["timestamp"], index_col="timestamp")


def test_validated_config_defaults() -> None:
    # Config determinista validada en el walk-forward de BTC/USDT (2026-06-21).
    assert settings.entry_confirmation_bars == 2
    assert settings.exit_confirmation_bars == 2
    assert settings.exit_buffer_pct == 0.02
    assert settings.cooldown_hours == 0
    assert settings.min_hold_hours == 0


def test_analyze_returns_valid_response() -> None:
    response = RegimeService().analyze(
        symbol="BTC/USDT",
        ohlcv_1h=_load("1h"),
        ohlcv_4h=_load("4h"),
    )

    assert isinstance(response, RegimeResponse)
    assert response.action in {"BUY", "HOLD", "CASH"}
    assert 0 <= response.confidence <= 100
    # No-lookahead: la decisión 4h es anterior al timestamp de ejecución 1h.
    assert response.decision_timestamp < response.timestamp


def test_service_signal_matches_validated_pipeline() -> None:
    """La señal en vivo == el pipeline validado (build_regime_signals + estado)."""
    df_1h_raw, df_4h_raw = _load("1h"), _load("4h")

    signal_df = build_regime_signals(
        add_core_indicators(df_1h_raw),
        add_core_indicators(df_4h_raw),
        entry_confirmation_bars=settings.entry_confirmation_bars,
        exit_confirmation_bars=settings.exit_confirmation_bars,
        exit_buffer_pct=settings.exit_buffer_pct,
    )
    positions = compute_position_state(
        signal_df,
        cooldown_hours=settings.cooldown_hours,
        min_hold_hours=settings.min_hold_hours,
    )

    response = RegimeService().analyze(
        symbol="BTC/USDT",
        ohlcv_1h=df_1h_raw,
        ohlcv_4h=df_4h_raw,
    )

    assert response.regime_on == bool(positions.iloc[-1])


def test_exit_buffer_makes_regime_stickier() -> None:
    df_1h = add_core_indicators(_load("1h"))
    df_4h = add_core_indicators(_load("4h"))

    def exposure(buffer: float) -> int:
        signal_df = build_regime_signals(
            df_1h, df_4h,
            entry_confirmation_bars=2,
            exit_confirmation_bars=2,
            exit_buffer_pct=buffer,
        )
        return int(compute_position_state(signal_df).sum())

    # El buffer endurece la salida: el régimen permanece activo al menos tanto.
    assert exposure(0.02) >= exposure(0.0)
