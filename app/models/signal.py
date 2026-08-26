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


class SignalAIOpinion(Base):
    """
    Opinión del LLM sobre una señal, registrada SIN afectar a la decisión.

    Existe para poder medir hacia adelante si la IA aporta: no se puede validar
    hacia atrás porque el modelo ya "conoce" el pasado (su entrenamiento incluye
    lo que ocurrió después de cualquier vela histórica). Acumulando opiniones
    emitidas ANTES de conocer el resultado se podrá responder con datos si
    filtrar por confianza habría mejorado el track record.

    NUNCA debe leerse desde la ruta de decisión. Es un observador.
    """

    __tablename__ = "signal_ai_opinions"
    __table_args__ = (
        UniqueConstraint("signal_id", name="uq_signal_ai_opinion_signal_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int] = mapped_column(
        ForeignKey("signals.id", ondelete="CASCADE"), index=True
    )

    # ok = interpretación válida | rejected = la barrera la tumbó | error = fallo técnico.
    # Los fallos se guardan a propósito: su frecuencia también es un dato.
    status: Mapped[str] = mapped_column(String(16))

    confidence: Mapped[int | None]
    reasoning: Mapped[str | None] = mapped_column(String, nullable=True)
    risk_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    error_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    model: Mapped[str] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
