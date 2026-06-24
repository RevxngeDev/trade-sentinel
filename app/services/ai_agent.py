"""Strictly bounded LLM interpretation for deterministic signal context."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Protocol

from pydantic import ValidationError

from app.config import settings
from app.core.groq_client import get_groq_client
from app.schemas.regime import AgentInterpretation, SignalRead


class AIInterpretationError(RuntimeError):
    """Raised when a valid bounded interpretation cannot be obtained."""


class InterpretationClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


class GroqInterpretationClient:
    """Small adapter that keeps Groq SDK details outside application logic."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = get_groq_client().chat.completions.create(
            model=settings.groq_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise AIInterpretationError("Groq returned an empty interpretation")
        return content


class AIInterpretationService:
    """Return an explanation without modifying a deterministic signal."""

    SYSTEM_PROMPT = """You interpret an existing educational crypto signal.
The deterministic rules engine has already chosen the action. You must not
change, recommend, repeat, or imply an action. Do not use action language such
as buy, sell, hold, cash, enter, exit, maintain a position, or stay out. You
must not predict prices, generate entry prices, stop losses, take profits, or
guarantee outcomes. Describe only facts explicitly present in the supplied
conditions and indicators. You may describe a technical structure as bullish
or bearish only when the supplied EMA and price relationships support it, and
you must state when that support is partial or incomplete. Never turn such a
description into advice or a prediction. An RSI above 50 is only above the
neutral threshold; call it overbought only when the supplied RSI is at least
70, and oversold only when it is at most 30. Do not repeat numeric prices or
numeric EMA/RSI values from the context. Return exactly one
JSON object with this schema:
{"confidence": integer 0-100, "reasoning": "Spanish text", "risk_notes": "Spanish text"}.
Do not include any other keys."""

    FORBIDDEN_ACTION_LANGUAGE = re.compile(
        r"\b(comprar|compra|vender|venta|mantener|mantén|mantenga|cash|"
        r"entrar|entra|entrada|salir|sale|salida|posición neutral|"
        r"fuera de posición|long|short|buy|sell|hold|exit)\b",
        re.IGNORECASE,
    )

    FORBIDDEN_FORECAST_LANGUAGE = re.compile(
        r"\b(reversi[oó]n|revirtiendo|pron[oó]stic[oa]|predicci[oó]n|"
        r"forecast|prediction)\b",
        re.IGNORECASE,
    )

    OVERBOUGHT_LANGUAGE = re.compile(
        r"\b(sobrecomprad[oa]|overbought)\b", re.IGNORECASE
    )
    OVERSOLD_LANGUAGE = re.compile(
        r"\b(sobrevendid[oa]|oversold)\b", re.IGNORECASE
    )

    def __init__(self, client: InterpretationClient | None = None) -> None:
        self.client = client or GroqInterpretationClient()

    async def interpret(self, signal: SignalRead) -> AgentInterpretation:
        user_prompt = json.dumps(
            {
                "pair": signal.pair,
                "timeframe": signal.timeframe,
                "deterministic_confidence": signal.confidence,
                "regime_on": signal.regime_on,
                "previous_regime_on": signal.previous_regime_on,
                "conditions": signal.conditions,
                "indicators": signal.indicators,
            },
            ensure_ascii=False,
        )

        last_error: Exception | None = None
        for _ in range(settings.ai_max_retries + 1):
            try:
                content = await asyncio.to_thread(
                    self.client.complete,
                    self.SYSTEM_PROMPT,
                    user_prompt,
                )
                interpretation = AgentInterpretation.model_validate_json(content)
                self._ensure_interpretive_only(interpretation, signal)
                return interpretation
            except (ValidationError, ValueError, AIInterpretationError) as exc:
                last_error = exc

        raise AIInterpretationError(
            "AI interpretation did not return valid schema-conforming JSON"
        ) from last_error

    @classmethod
    def _ensure_interpretive_only(
        cls, interpretation: AgentInterpretation, signal: SignalRead
    ) -> None:
        text = f"{interpretation.reasoning} {interpretation.risk_notes}"
        if cls.FORBIDDEN_ACTION_LANGUAGE.search(text):
            raise AIInterpretationError(
                "AI interpretation contained prohibited action language"
            )
        if cls.FORBIDDEN_FORECAST_LANGUAGE.search(text):
            raise AIInterpretationError(
                "AI interpretation contained prohibited forecast language"
            )
        if cls._contains_observed_values(text, signal):
            raise AIInterpretationError(
                "AI interpretation repeated observed numeric market values"
            )

        rsi = signal.indicators.get("rsi_14")
        if isinstance(rsi, (int, float)):
            if rsi < 70 and cls.OVERBOUGHT_LANGUAGE.search(text):
                raise AIInterpretationError(
                    "AI interpretation called an RSI below 70 overbought"
                )
            if rsi > 30 and cls.OVERSOLD_LANGUAGE.search(text):
                raise AIInterpretationError(
                    "AI interpretation called an RSI above 30 oversold"
                )

    @staticmethod
    def _contains_observed_values(text: str, signal: SignalRead) -> bool:
        values = [signal.price, *signal.indicators.values()]
        for value in values:
            if not isinstance(value, (int, float)):
                continue
            rendered = {
                str(value),
                f"{value:.1f}",
                f"{value:.2f}",
                f"{value:,.2f}",
            }
            if any(candidate in text for candidate in rendered):
                return True
        return False
