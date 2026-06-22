"""
Definición del régimen alcista defensivo — fuente única de verdad.

Antes estaba triplicada (audit, v2 y RegimeService), con riesgo de divergencia.
Estas funciones puras operan sobre un DataFrame con indicadores ya calculados
(ver app.core.indicators) y son compartidas por backtest y API.

No-lookahead: `decision_regime_on` usa el régimen de la vela anterior (shift 1).
"""

from __future__ import annotations

import pandas as pd

REGIME_CONDITION_COLUMNS = [
    "condition_close_above_ema50",
    "condition_close_above_ema200",
    "condition_ema50_above_ema200",
    "condition_ema50_rising",
    "condition_ema200_rising",
    "condition_rsi_above_50",
]


def add_regime_conditions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Añade las 6 condiciones del régimen super-strict bullish, el régimen crudo
    (`raw_regime_on`) y el régimen de decisión sin lookahead (`decision_regime_on`).
    """
    out = df.copy()

    out["condition_close_above_ema50"] = out["close"] > out["ema_50"]
    out["condition_close_above_ema200"] = out["close"] > out["ema_200"]
    out["condition_ema50_above_ema200"] = out["ema_50"] > out["ema_200"]
    out["condition_ema50_rising"] = out["ema_50"] > out["ema_50"].shift(6)
    out["condition_ema200_rising"] = out["ema_200"] > out["ema_200"].shift(6)
    out["condition_rsi_above_50"] = out["rsi_14"] > 50

    raw = out[REGIME_CONDITION_COLUMNS[0]]
    for column in REGIME_CONDITION_COLUMNS[1:]:
        raw = raw & out[column]

    out["raw_regime_on"] = raw.fillna(False).astype(bool)

    # No-lookahead: solo usamos el régimen confirmado de la vela anterior.
    out["decision_regime_on"] = (
        out["raw_regime_on"].shift(1, fill_value=False).astype(bool)
    )
    out["decision_timestamp"] = out.index.to_series().shift(1)

    return out


def confirmation_ready(decision: pd.Series, bars: int) -> pd.Series:
    """True cuando `decision` se mantuvo True las últimas `bars` velas."""
    return (
        decision.rolling(bars)
        .sum()
        .eq(bars)
        .fillna(False)
        .astype(bool)
    )


def exit_buffer_mask(
    close: pd.Series,
    ema: pd.Series,
    exit_buffer_pct: float,
) -> pd.Series:
    """
    True cuando el precio cayó al menos `exit_buffer_pct` por debajo de la EMA.
    Con buffer 0.0 devuelve todo True (no restringe la salida).
    """
    if exit_buffer_pct <= 0.0:
        return pd.Series(True, index=close.index)

    return (close < ema * (1.0 - exit_buffer_pct)).fillna(False).astype(bool)
