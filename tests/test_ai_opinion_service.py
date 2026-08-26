"""
Tests del registro de opiniones de IA.

El invariante que protegen: la IA es un OBSERVADOR. Nunca decide, y ningún
fallo suyo puede impedir que se capture o se alerte una señal.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.config import Settings, settings
from app.schemas.regime import SignalRead
from app.services.ai_agent import AIInterpretationError
from app.services.ai_opinion_service import AIOpinionService


def _signal(signal_id: int = 1) -> SignalRead:
    return SignalRead(
        id=signal_id,
        pair="BTC/USDT",
        timeframe="4h",
        action="CASH",
        regime_on=False,
        previous_regime_on=False,
        confidence=70,
        price=65000.0,
        signal_timestamp=datetime(2026, 8, 26, 8, tzinfo=timezone.utc),
        decision_timestamp=datetime(2026, 8, 26, 4, tzinfo=timezone.utc),
        conditions={"rsi_above_50": False},
        indicators={"rsi_14": 45.0},
        reasoning="deterministic reasoning",
        created_at=datetime(2026, 8, 26, 8, 1, tzinfo=timezone.utc),
    )


class FakeStore:
    def __init__(self, fail: bool = False) -> None:
        self.saved: list[dict] = []
        self.fail = fail

    async def insert_if_absent(self, payload: dict):
        if self.fail:
            raise RuntimeError("supabase down")
        self.saved.append(payload)
        return None

    async def list_opinions(self, limit: int):
        return []


class FakeInterpreter:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    async def interpret(self, signal: SignalRead):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "ai_opinion_logging_enabled", True)


# ============================================================
# Interruptor
# ============================================================


def test_opinion_logging_disabled_by_default() -> None:
    """Hace red y consume cuota: debe exigir activación explícita."""
    assert Settings(_env_file=None).ai_opinion_logging_enabled is False


async def test_disabled_does_not_call_the_llm(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_opinion_logging_enabled", False)
    interpreter = FakeInterpreter(result=None)
    store = FakeStore()

    result = await AIOpinionService(interpreter, store).record_for_signal(_signal())

    assert result is None
    assert interpreter.calls == 0
    assert store.saved == []


# ============================================================
# Registro
# ============================================================


async def test_records_successful_opinion(enabled) -> None:
    from app.schemas.regime import AgentInterpretation

    interpreter = FakeInterpreter(
        result=AgentInterpretation(
            confidence=42,
            reasoning="La estructura técnica es parcial.",
            risk_notes="Contexto incompleto.",
        )
    )
    store = FakeStore()

    await AIOpinionService(interpreter, store).record_for_signal(_signal(7))

    assert len(store.saved) == 1
    saved = store.saved[0]
    assert saved["signal_id"] == 7
    assert saved["status"] == "ok"
    assert saved["confidence"] == 42
    assert saved["error_reason"] is None
    assert saved["model"] == settings.groq_model


async def test_records_guardrail_rejection_instead_of_dropping_it(enabled) -> None:
    """La frecuencia de rechazos es un dato; no debe perderse en silencio."""
    interpreter = FakeInterpreter(error=AIInterpretationError("action language"))
    store = FakeStore()

    await AIOpinionService(interpreter, store).record_for_signal(_signal())

    assert store.saved[0]["status"] == "rejected"
    assert "action language" in store.saved[0]["error_reason"]
    assert store.saved[0]["confidence"] is None


async def test_records_technical_failure_as_error(enabled) -> None:
    interpreter = FakeInterpreter(error=RuntimeError("groq timeout"))
    store = FakeStore()

    await AIOpinionService(interpreter, store).record_for_signal(_signal())

    assert store.saved[0]["status"] == "error"
    assert "groq timeout" in store.saved[0]["error_reason"]


async def test_store_failure_never_propagates(enabled) -> None:
    """Un fallo al guardar telemetría no puede tumbar la captura."""
    from app.schemas.regime import AgentInterpretation

    interpreter = FakeInterpreter(
        result=AgentInterpretation(confidence=50, reasoning="x", risk_notes="y")
    )

    result = await AIOpinionService(interpreter, FakeStore(fail=True)).record_for_signal(
        _signal()
    )

    assert result is None


# ============================================================
# Invariante: la IA no decide
# ============================================================


async def test_opinion_never_reaches_the_stored_action(enabled) -> None:
    """
    Aunque el LLM opine con confianza mínima, la acción persistida no cambia.
    El registro es telemetría, no un filtro.
    """
    from app.schemas.regime import AgentInterpretation

    signal = _signal()
    original_action = signal.action

    interpreter = FakeInterpreter(
        result=AgentInterpretation(
            confidence=0,
            reasoning="Soporte muy incompleto.",
            risk_notes="Riesgo alto.",
        )
    )
    store = FakeStore()

    await AIOpinionService(interpreter, store).record_for_signal(signal)

    assert signal.action == original_action
    assert "action" not in store.saved[0]
