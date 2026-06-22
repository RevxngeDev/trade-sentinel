from __future__ import annotations

import pandas as pd

from app.config import settings
from app.core.indicators import add_core_indicators
from app.core.regime import add_regime_conditions
from app.core.signals import build_regime_signals, compute_position_state
from app.schemas.regime import (
    RegimeConditions,
    RegimeIndicators,
    RegimeResponse,
)

MIN_CANDLES = 220  # EMA200 + margen


class RegimeService:
    """
    Genera la señal de régimen en vivo usando EXACTAMENTE el pipeline validado:
    régimen 4h -> confirmation bars -> reindex a 1h -> exit buffer 1h ->
    máquina de estado (cooldown/min-hold). La acción resulta del estado de
    posición, idéntico al backtest.
    """

    def __init__(
        self,
        entry_confirmation_bars: int | None = None,
        exit_confirmation_bars: int | None = None,
        exit_buffer_pct: float | None = None,
        cooldown_hours: int | None = None,
        min_hold_hours: int | None = None,
    ) -> None:
        self.entry_confirmation_bars = (
            entry_confirmation_bars or settings.entry_confirmation_bars
        )
        self.exit_confirmation_bars = (
            exit_confirmation_bars or settings.exit_confirmation_bars
        )
        self.exit_buffer_pct = (
            settings.exit_buffer_pct if exit_buffer_pct is None else exit_buffer_pct
        )
        self.cooldown_hours = (
            settings.cooldown_hours if cooldown_hours is None else cooldown_hours
        )
        self.min_hold_hours = (
            settings.min_hold_hours if min_hold_hours is None else min_hold_hours
        )

    def analyze(
        self,
        symbol: str,
        ohlcv_1h: pd.DataFrame,
        ohlcv_4h: pd.DataFrame,
    ) -> RegimeResponse:
        df_1h = add_core_indicators(ohlcv_1h)
        df_4h = add_core_indicators(ohlcv_4h)

        if len(df_1h) < MIN_CANDLES or len(df_4h) < MIN_CANDLES:
            raise ValueError(
                "Not enough candles to calculate EMA200 and regime conditions "
                f"(need >= {MIN_CANDLES} en 1h y 4h)."
            )

        signal_df = build_regime_signals(
            df_1h=df_1h,
            df_4h=df_4h,
            entry_confirmation_bars=self.entry_confirmation_bars,
            exit_confirmation_bars=self.exit_confirmation_bars,
            exit_buffer_pct=self.exit_buffer_pct,
        )

        positions = compute_position_state(
            signal_df,
            cooldown_hours=self.cooldown_hours,
            min_hold_hours=self.min_hold_hours,
        )

        current_in_position = bool(positions.iloc[-1])
        previous_in_position = bool(positions.iloc[-2]) if len(positions) >= 2 else False

        # Régimen 4h y la vela 4h cerrada que dirige la decisión actual.
        regime_4h = add_regime_conditions(df_4h)
        decision_row_4h = (
            regime_4h.iloc[-2] if len(regime_4h) >= 2 else regime_4h.iloc[-1]
        )

        action = self._resolve_action(current_in_position, previous_in_position)
        confidence = self._calculate_confidence(decision_row_4h, current_in_position)
        reasoning = self._build_reasoning(action, decision_row_4h)

        return RegimeResponse(
            symbol=symbol,
            timeframe=settings.regime_base_timeframe,
            action=action,
            regime_on=current_in_position,
            previous_regime_on=previous_in_position,
            confidence=confidence,
            price=float(signal_df["close"].iloc[-1]),
            timestamp=signal_df.index[-1].to_pydatetime(),
            decision_timestamp=decision_row_4h.name.to_pydatetime(),
            indicators=RegimeIndicators(
                close=float(decision_row_4h["close"]),
                ema_50=float(decision_row_4h["ema_50"]),
                ema_200=float(decision_row_4h["ema_200"]),
                rsi_14=float(decision_row_4h["rsi_14"]),
            ),
            conditions=RegimeConditions(
                close_above_ema50=bool(decision_row_4h["condition_close_above_ema50"]),
                close_above_ema200=bool(decision_row_4h["condition_close_above_ema200"]),
                ema50_above_ema200=bool(decision_row_4h["condition_ema50_above_ema200"]),
                ema50_rising=bool(decision_row_4h["condition_ema50_rising"]),
                ema200_rising=bool(decision_row_4h["condition_ema200_rising"]),
                rsi_above_50=bool(decision_row_4h["condition_rsi_above_50"]),
            ),
            reasoning=reasoning,
            warning=(
                "Señal educativa para paper trading. No es asesoría financiera "
                "ni recomendación garantizada."
            ),
        )

    @staticmethod
    def _resolve_action(current_in_position: bool, previous_in_position: bool) -> str:
        if current_in_position and not previous_in_position:
            return "BUY"
        if current_in_position and previous_in_position:
            return "HOLD"
        return "CASH"

    @staticmethod
    def _calculate_confidence(row: pd.Series, in_position: bool) -> int:
        conditions = [
            bool(row["condition_close_above_ema50"]),
            bool(row["condition_close_above_ema200"]),
            bool(row["condition_ema50_above_ema200"]),
            bool(row["condition_ema50_rising"]),
            bool(row["condition_ema200_rising"]),
            bool(row["condition_rsi_above_50"]),
        ]
        base_confidence = int((sum(conditions) / len(conditions)) * 100)

        if in_position:
            return min(95, max(65, base_confidence))
        return min(80, base_confidence)

    @staticmethod
    def _build_reasoning(action: str, row: pd.Series) -> str:
        if action == "BUY":
            return (
                "BTC acaba de entrar en régimen alcista defensivo confirmado. "
                "La exposición está permitida para paper trading, manteniendo "
                "control de riesgo y seguimiento posterior."
            )

        if action == "HOLD":
            return (
                "BTC mantiene régimen alcista defensivo. La señal sugiere mantener "
                "exposición en paper trading mientras las condiciones sigan activas."
            )

        failed = []
        if not bool(row["condition_close_above_ema50"]):
            failed.append("el precio no está por encima de la EMA50")
        if not bool(row["condition_close_above_ema200"]):
            failed.append("el precio no está por encima de la EMA200")
        if not bool(row["condition_ema50_above_ema200"]):
            failed.append("la EMA50 no está por encima de la EMA200")
        if not bool(row["condition_ema50_rising"]):
            failed.append("la EMA50 no está subiendo")
        if not bool(row["condition_ema200_rising"]):
            failed.append("la EMA200 no está subiendo")
        if not bool(row["condition_rsi_above_50"]):
            failed.append("el RSI 4h no está por encima de 50")

        if failed:
            return (
                "BTC no cumple el régimen alcista defensivo porque "
                + ", ".join(failed)
                + ". La señal actual es mantenerse en cash o fuera de posición."
            )

        return (
            "BTC no tiene régimen confirmado suficiente. La señal actual es "
            "mantenerse en cash."
        )
