"""
Modelos de persistencia.

`Signal` está adaptado a la estrategia de RÉGIMEN (acción de asignación
BUY/HOLD/CASH + snapshot de condiciones), NO al esquema entry/SL/TP del
ARCHITECTURE original, porque la estrategia validada no produce stop-loss /
take-profit. `SignalResult` registra el resultado al evaluar la señal.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        # Una sola señal por par y vela de ejecución (evita duplicados).
        UniqueConstraint("pair", "signal_timestamp", name="uq_signal_pair_ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    pair: Mapped[str] = mapped_column(String(20), index=True)
    timeframe: Mapped[str] = mapped_column(String(5))

    action: Mapped[str] = mapped_column(String(8))  # BUY | HOLD | CASH
    regime_on: Mapped[bool]
    previous_regime_on: Mapped[bool]
    confidence: Mapped[int]

    # Precio de la vela de ejecución (1h) en el momento de la señal.
    price: Mapped[float]

    signal_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    decision_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Snapshots para auditoría / explicación (sin precios inventados).
    conditions: Mapped[dict] = mapped_column(JSON)
    indicators: Mapped[dict] = mapped_column(JSON)
    reasoning: Mapped[str] = mapped_column(String)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    results: Mapped[list["SignalResult"]] = relationship(
        back_populates="signal",
        cascade="all, delete-orphan",
    )


class SignalResult(Base):
    __tablename__ = "signal_results"
    __table_args__ = (
        UniqueConstraint("signal_id", name="uq_signal_result_signal_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int] = mapped_column(
        ForeignKey("signals.id", ondelete="CASCADE"), index=True
    )

    # Resultado del seguimiento (Fase 4). Para régimen: retorno forward, etc.
    outcome: Mapped[str] = mapped_column(String(16))
    pnl_pct: Mapped[float | None]
    evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    signal: Mapped["Signal"] = relationship(back_populates="results")
