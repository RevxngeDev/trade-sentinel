from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.regime import SignalRead
from app.services.ai_agent import AIInterpretationService


def _signal() -> SignalRead:
    timestamp = datetime(2026, 6, 22, 18, 0, tzinfo=timezone.utc)
    return SignalRead(
        id=1,
        pair="BTC/USDT",
        timeframe="4h",
        action="CASH",
        regime_on=False,
        previous_regime_on=False,
        confidence=50,
        price=1.0,
        signal_timestamp=timestamp,
        decision_timestamp=timestamp,
        conditions={"ema50_above_ema200": False},
        indicators={"rsi_14": 58.5},
        reasoning="Deterministic rules keep the strategy in cash.",
        created_at=timestamp,
    )


class FakeInterpretationClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.responses.pop(0)


async def test_interpretation_returns_valid_bounded_json() -> None:
    client = FakeInterpretationClient(
        [
            '{"confidence": 42, "reasoning": "Las condiciones son mixtas.", '
            '"risk_notes": "La tendencia principal sigue débil."}'
        ]
    )
    service = AIInterpretationService(client=client)

    interpretation = await service.interpret(_signal())

    assert interpretation.confidence == 42
    assert "mixtas" in interpretation.reasoning
    assert len(client.calls) == 1
    assert '"action"' not in client.calls[0][1]


async def test_interpretation_retries_when_response_tries_to_choose_action() -> None:
    client = FakeInterpretationClient(
        [
            '{"action": "BUY", "confidence": 99, "reasoning": "x", '
            '"risk_notes": "x"}',
            '{"confidence": 40, "reasoning": "Contexto limitado.", '
            '"risk_notes": "La volatilidad puede cambiar el contexto."}',
        ]
    )
    service = AIInterpretationService(client=client)

    interpretation = await service.interpret(_signal())

    assert interpretation.confidence == 40
    assert len(client.calls) == 2


async def test_interpretation_retries_when_text_recommends_an_action() -> None:
    client = FakeInterpretationClient(
        [
            '{"confidence": 50, "reasoning": "Se recomienda mantener cash.", '
            '"risk_notes": "Evitar entradas."}',
            '{"confidence": 48, "reasoning": "Las condiciones de tendencia son incompletas.", '
            '"risk_notes": "La volatilidad puede invalidar rápidamente el contexto."}',
        ]
    )
    service = AIInterpretationService(client=client)

    interpretation = await service.interpret(_signal())

    assert interpretation.confidence == 48
    assert len(client.calls) == 2
