"""
Señales de la estrategia de régimen — fuente única (backtest + API en vivo).

`build_regime_signals` arma la señal multi-timeframe (régimen 4h reindexado a 1h
con confirmation bars + exit buffer). `compute_position_state` es la máquina de
estado de posición (cooldown + min-hold) usada tanto por el motor de backtest
como por el servicio en vivo, para que la señal servida == la validada.

No-lookahead garantizado por `decision_regime_on` (régimen de la vela 4h anterior).
"""

from __future__ import annotations

import pandas as pd

from app.core.regime import (
    add_regime_conditions,
    confirmation_ready,
    exit_buffer_mask,
)


def build_regime_signals(
    df_1h: pd.DataFrame,
    df_4h: pd.DataFrame,
    *,
    entry_confirmation_bars: int = 1,
    exit_confirmation_bars: int = 1,
    exit_buffer_pct: float = 0.0,
) -> pd.DataFrame:
    regime_4h = add_regime_conditions(df_4h)
    decision = regime_4h["decision_regime_on"]

    entry_ready_4h = confirmation_ready(decision, entry_confirmation_bars)
    exit_ready_4h = confirmation_ready(~decision, exit_confirmation_bars)

    signal_df = df_1h.copy()

    def _to_1h(series: pd.Series) -> pd.Series:
        aligned = series.reindex(signal_df.index, method="ffill")
        return aligned.where(aligned.notna(), other=False).astype(bool)

    signal_df["decision_regime_on"] = _to_1h(decision)
    signal_df["entry_ready"] = _to_1h(entry_ready_4h)

    # Exit buffer evaluado en 1h (precio vs EMA50 de la vela 1h).
    exit_regime_off = _to_1h(exit_ready_4h)
    signal_df["exit_ready"] = exit_regime_off & exit_buffer_mask(
        signal_df["close"], signal_df["ema_50"], exit_buffer_pct
    )

    return signal_df


def compute_position_state(
    signal_df: pd.DataFrame,
    *,
    cooldown_hours: int = 0,
    min_hold_hours: int = 0,
) -> pd.Series:
    """
    Máquina de estado de posición (sin contabilidad de capital).

    Reglas idénticas al motor de backtest:
    - Entra si está flat, `entry_ready` y cooldown cumplido.
    - Sale si está en posición, `exit_ready` y min_hold cumplido.

    Devuelve la serie booleana `in_position` (estado POST-acción de cada vela).
    """
    in_position = False
    entry_time: pd.Timestamp | None = None
    cooldown_until: pd.Timestamp | None = None

    states: list[bool] = []

    for timestamp, row in signal_df.iterrows():
        can_enter = cooldown_until is None or timestamp >= cooldown_until

        if not in_position and bool(row["entry_ready"]) and can_enter:
            in_position = True
            entry_time = timestamp
        elif in_position and bool(row["exit_ready"]):
            holding_hours = int((timestamp - entry_time).total_seconds() // 3600)
            if holding_hours >= min_hold_hours:
                in_position = False
                cooldown_until = timestamp + pd.Timedelta(hours=cooldown_hours)
                entry_time = None

        states.append(in_position)

    return pd.Series(states, index=signal_df.index, name="in_position")
