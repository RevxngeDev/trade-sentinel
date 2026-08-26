from __future__ import annotations

import pytest

from app.core.signals import build_regime_signals
from backtest.common import FROZEN_DATA_DIR, load_pair_data
from backtest.engine import build_metrics, run_position_backtest
import backtest.run_btc_regime_v2_no_lookahead as v2


# Estas guardas comparan contra números documentados, así que deben leer el
# dataset CONGELADO. Los CSV de data/ se refrescan vía ccxt y sus cifras cambian.
pytestmark = pytest.mark.skipif(
    not (FROZEN_DATA_DIR / "BTC_USDT_4h.csv").exists(),
    reason="Falta el dataset BTC congelado en data/frozen/",
)


def _frozen_btc() -> tuple:
    return load_pair_data("BTC/USDT", data_dir=FROZEN_DATA_DIR)


def _audit_metrics() -> dict:
    df_1h, df_4h = _frozen_btc()
    signal_df = build_regime_signals(df_1h, df_4h)
    trades_df, equity_curve_df = run_position_backtest(signal_df, symbol="BTC/USDT")
    return build_metrics(df_1h=df_1h, trades_df=trades_df, equity_curve_df=equity_curve_df)


def test_audit_equals_v2_with_bars_one() -> None:
    """El audit base es el caso particular del motor v2 (bars=1, sin buffer)."""
    audit = _audit_metrics()

    df_1h, df_4h = _frozen_btc()
    row, _, _ = v2.run_config(
        period="full",
        df_1h=df_1h,
        df_4h=df_4h,
        entry_confirmation_bars=1,
        exit_confirmation_bars=1,
        cooldown_hours=0,
        min_hold_hours=0,
        exit_buffer_pct=0.0,
    )

    assert audit["total_trades"] == row["total_trades"]
    assert audit["total_return_pct"] == pytest.approx(row["total_return_pct"], abs=1e-9)


def test_audit_regression_guard() -> None:
    """Guarda de regresión sobre el refactor de la fuente única de indicadores."""
    audit = _audit_metrics()

    # El benchmark depende solo del dataset (inicio alineado con min_periods).
    assert audit["benchmark_return_pct"] == pytest.approx(-2.05, abs=0.05)
    assert audit["total_trades"] == 90
    assert audit["total_return_pct"] > 0
