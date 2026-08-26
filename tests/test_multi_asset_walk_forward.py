"""Tests de la lógica del walk-forward multi-activo (sin red ni CSV reales)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.common import FROZEN_DATA_DIR, generate_walk_forward_windows
from backtest.run_multi_asset_walk_forward import (
    MIN_WINDOW_BARS,
    build_asset_summary,
    compound,
    evaluate_asset,
    evaluate_window,
)


def _hourly_frame(hours: int, start: str = "2024-01-01") -> pd.DataFrame:
    index = pd.date_range(start=start, periods=hours, freq="h", tz="UTC")
    return pd.DataFrame({"close": np.linspace(100, 200, hours)}, index=index)


# ============================================================
# Ventanas
# ============================================================


def test_windows_are_contiguous_and_non_overlapping() -> None:
    """Los tests deben encadenar sin solaparse; si no, componerlos mentiría."""
    df = _hourly_frame(hours=24 * 500)

    windows = generate_walk_forward_windows(df, train_days=270, test_days=60)

    assert len(windows) > 1
    for previous, current in zip(windows, windows[1:]):
        assert previous["test_end"] == current["test_start"]


def test_windows_never_exceed_available_data() -> None:
    df = _hourly_frame(hours=24 * 400)

    windows = generate_walk_forward_windows(df, train_days=270, test_days=60)

    for window in windows:
        assert window["test_end"] <= df.index.max()
        # El train siempre precede al test: no se evalúa con datos ya vistos.
        assert window["train_end"] == window["test_start"]


def test_windows_empty_when_history_too_short() -> None:
    df = _hourly_frame(hours=24 * 100)

    assert generate_walk_forward_windows(df, train_days=270, test_days=60) == []


# ============================================================
# Composición de retornos
# ============================================================


def test_compound_chains_percentages() -> None:
    assert compound([10, 10]) == pytest.approx(21.0)
    assert compound([50, -50]) == pytest.approx(-25.0)
    assert compound([]) == pytest.approx(0.0)


def test_compound_is_not_a_plain_sum() -> None:
    """Sumar retornos de ventanas encadenadas exagera el resultado."""
    returns = [20, 20, 20]

    assert compound(returns) == pytest.approx(72.8)
    assert compound(returns) != pytest.approx(sum(returns))


# ============================================================
# Evaluación de ventana
# ============================================================


def test_evaluate_window_skips_short_windows() -> None:
    signal_df = _hourly_frame(hours=MIN_WINDOW_BARS - 1)

    result = evaluate_window(
        signal_df,
        symbol="BTC/USDT",
        start=signal_df.index.min(),
        end=signal_df.index.max(),
    )

    assert result is None


# ============================================================
# Resumen por activo
# ============================================================


def _fold(fold: int, strategy: float, benchmark: float) -> dict:
    return {
        "symbol": "BTC/USDT",
        "fold": fold,
        "total_return_pct": strategy,
        "benchmark_return_pct": benchmark,
        "max_drawdown_pct": 5.0,
        "benchmark_drawdown_pct": 12.0,
        "total_trades": 3,
        "exposure_pct": 40.0,
    }


def test_summary_counts_positive_and_beating_folds() -> None:
    signal_df = _hourly_frame(hours=1000)
    fold_rows = [
        _fold(1, strategy=10.0, benchmark=5.0),    # positivo y bate
        _fold(2, strategy=-4.0, benchmark=-10.0),  # negativo pero bate
        _fold(3, strategy=2.0, benchmark=8.0),     # positivo y no bate
    ]

    summary = build_asset_summary(
        symbol="BTC/USDT",
        fold_rows=fold_rows,
        full_metrics=None,
        signal_df=signal_df,
    )

    assert summary["folds"] == 3
    assert summary["wf_positive_folds"] == 2
    assert summary["wf_beat_benchmark_folds"] == 2
    assert summary["wf_return_pct"] == pytest.approx(compound([10.0, -4.0, 2.0]))
    assert summary["wf_benchmark_pct"] == pytest.approx(compound([5.0, -10.0, 8.0]))
    assert summary["wf_excess_pp"] == pytest.approx(
        summary["wf_return_pct"] - summary["wf_benchmark_pct"]
    )
    assert summary["wf_worst_fold_return_pct"] == pytest.approx(-4.0)
    assert summary["wf_total_trades"] == 9


def test_summary_survives_asset_without_folds() -> None:
    """Un activo con histórico corto no debe romper el informe completo."""
    signal_df = _hourly_frame(hours=500)

    summary = build_asset_summary(
        symbol="SOL/USDT",
        fold_rows=[],
        full_metrics=None,
        signal_df=signal_df,
    )

    assert summary["folds"] == 0
    assert "wf_return_pct" not in summary


# ============================================================
# Guarda de regresión contra el walk-forward documentado
# ============================================================


@pytest.mark.skipif(
    not (FROZEN_DATA_DIR / "BTC_USDT_4h.csv").exists(),
    reason="Falta el dataset BTC congelado en data/frozen/",
)
def test_frozen_btc_reproduces_documented_walk_forward() -> None:
    """
    Sobre el dataset congelado, este walk-forward debe reproducir el resultado
    documentado el 2026-06-21 para la config fija de BTC: ~+18% agregado (suma
    de folds) y 4/7 folds positivos. Si esto cambia, el motor o la definición de
    las ventanas se movió y la comparación con lo validado deja de valer.
    """
    fold_rows, summary = evaluate_asset(
        "BTC/USDT",
        refresh=False,
        train_days=270,
        test_days=60,
        data_dir=FROZEN_DATA_DIR,
    )

    fold_returns = [row["total_return_pct"] for row in fold_rows]

    assert summary["folds"] == 7
    assert sum(fold_returns) == pytest.approx(18.24, abs=0.5)
    assert summary["wf_positive_folds"] == 4
    # El overlay defensivo debe seguir recortando el drawdown del benchmark.
    assert summary["wf_avg_drawdown_pct"] < summary["wf_avg_benchmark_drawdown_pct"]
