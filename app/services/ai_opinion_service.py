"""
Registro de opiniones del LLM sobre señales deterministas (observador puro).

POR QUÉ EXISTE
--------------
No se puede validar hacia atrás si la IA aporta a una decisión de trading: un
LLM entrenado hasta hoy ya "conoce" lo que pasó después de cualquier vela
histórica, así que un backtest de IA sale bien por memoria, no por predicción.
Es lookahead en su forma más difícil de detectar.

La única medición honesta es hacia adelante: registrar la opinión ANTES de
conocer el resultado y acumular muestra. Con suficientes pares
(opinión, resultado real) se podrá responder con datos si filtrar las señales de
baja confianza habría mejorado el track record.

INVARIANTE
----------
Este servicio NUNCA debe influir en la acción. La acción sigue saliendo del
pipeline determinista. Aquí solo se observa y se guarda; cualquier fallo se
registra y se traga, para que un problema con la IA no pueda detener la captura.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.schemas.regime import SignalAIOpinionRead, SignalRead
from app.services.ai_agent import AIInterpretationError, AIInterpretationService
from app.services.signal_store import AIOpinionStore, SupabaseAIOpinionStore

logger = logging.getLogger(__name__)


class AIOpinionService:
    """Pide una interpretación al LLM y la guarda junto a la señal."""

    def __init__(
        self,
        interpreter: AIInterpretationService | None = None,
        store: AIOpinionStore | None = None,
    ) -> None:
        self._interpreter = interpreter
        self.store = store or SupabaseAIOpinionStore()

    @property
    def interpreter(self) -> AIInterpretationService:
        # Perezoso: construir el cliente Groq exige API key, y el servicio debe
        # poder instanciarse sin ella cuando el registro está desactivado.
        if self._interpreter is None:
            self._interpreter = AIInterpretationService()
        return self._interpreter

    async def record_for_signal(self, signal: SignalRead) -> SignalAIOpinionRead | None:
        """
        Registra la opinión del LLM para una señal ya persistida.

        Devuelve None si está desactivado o si no se pudo guardar. El llamador
        debe IGNORAR el valor de retorno para decidir: es telemetría.
        """
        if not settings.ai_opinion_logging_enabled:
            return None

        payload = await self._build_payload(signal)

        try:
            return await self.store.insert_if_absent(payload)
        except Exception:  # noqa: BLE001 - registrar no puede tumbar la captura
            logger.exception(
                "No se pudo guardar la opinión de IA para la señal %s.", signal.id
            )
            return None

    async def _build_payload(self, signal: SignalRead) -> dict:
        base = {
            "signal_id": signal.id,
            "model": settings.groq_model,
            "confidence": None,
            "reasoning": None,
            "risk_notes": None,
            "error_reason": None,
        }

        try:
            interpretation = await self.interpreter.interpret(signal)
        except AIInterpretationError as exc:
            # La barrera interpretativa tumbó la respuesta tras los reintentos.
            # Su frecuencia es un dato en sí misma, así que se guarda.
            logger.warning("Opinión de IA rechazada para la señal %s: %s", signal.id, exc)
            return {**base, "status": "rejected", "error_reason": str(exc)[:500]}
        except Exception as exc:  # noqa: BLE001 - red, cuota, timeout...
            logger.warning("Opinión de IA falló para la señal %s: %s", signal.id, exc)
            return {**base, "status": "error", "error_reason": str(exc)[:500]}

        return {
            **base,
            "status": "ok",
            "confidence": interpretation.confidence,
            "reasoning": interpretation.reasoning,
            "risk_notes": interpretation.risk_notes,
        }
