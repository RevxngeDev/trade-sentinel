from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RegimeAction = Literal["BUY", "HOLD", "CASH"]


class RegimeConditions(BaseModel):
    close_above_ema50: bool
    close_above_ema200: bool
    ema50_above_ema200: bool
    ema50_rising: bool
    ema200_rising: bool
    rsi_above_50: bool


class RegimeIndicators(BaseModel):
    close: float
    ema_50: float
    ema_200: float
    rsi_14: float


class RegimeResponse(BaseModel):
    symbol: str
    timeframe: str
    action: RegimeAction
    regime_on: bool
    previous_regime_on: bool
    confidence: int = Field(ge=0, le=100)

    # Precio de la vela de ejecución (1h) en el momento de la señal.
    price: float

    timestamp: datetime
    decision_timestamp: datetime

    indicators: RegimeIndicators
    conditions: RegimeConditions

    reasoning: str
    warning: str


class SignalRead(BaseModel):
    """Vista de una señal persistida (lectura desde la DB)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    pair: str
    timeframe: str
    action: RegimeAction
    regime_on: bool
    previous_regime_on: bool
    confidence: int
    price: float
    signal_timestamp: datetime
    decision_timestamp: datetime
    conditions: dict
    indicators: dict
    reasoning: str
    created_at: datetime


TrackingOutcome = Literal["gain", "loss", "flat", "cash"]


class SignalResultRead(BaseModel):
    id: int
    signal_id: int
    outcome: TrackingOutcome
    pnl_pct: float | None
    evaluated_at: datetime | None


class TrackingRunRead(BaseModel):
    scanned: int
    eligible: int
    created: int
    skipped_existing: int


class SignalStatsRead(BaseModel):
    total_signals: int
    evaluated_signals: int
    pending_signals: int
    active_signals: int
    cash_signals: int
    active_win_rate_pct: float | None
    average_active_return_pct: float | None
    average_signal_return_pct: float | None
    tracking_horizon_hours: int
