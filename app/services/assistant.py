"""
Asistente conversacional del proyecto (Hito 1 de ASSISTANT_PLAN).

Responde preguntas sobre ESTE proyecto usando herramientas de solo lectura y los
documentos ingestados. No es un oráculo de mercado: no predice precios ni da
consejo financiero personalizado.

Las cuatro reglas innegociables (ASSISTANT_PLAN §8) viven en el prompt Y en el
código: el modelo no puede calcular números porque no se le dan datos en el
prompt — solo los que devuelven las herramientas.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.core.groq_client import get_groq_client
from app.services.assistant_tools import get_callable, tool_specs

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres el asistente de TradeSentinel, un proyecto educativo de señales
de cripto. Ayudas a su dueño a entender SU propio sistema y SU propio historial.

REGLAS INNEGOCIABLES:
1. NUNCA inventes un número. Toda cifra debe venir de una herramienta. Si no tienes la
   herramienta adecuada, di que no puedes consultarlo.
2. Di siempre el tamaño de muestra cuando hables de rendimiento (nº de operaciones o de
   señales). Una muestra pequeña no demuestra nada y debes decirlo.
3. NUNCA predigas precios ni des consejo financiero personalizado (cuánto invertir, si
   comprar o vender). Puedes explicar qué hace el sistema y qué dicen los datos.
4. Si no puedes respaldar algo con una herramienta o un documento, di que no lo sabes.

CÓMO TRABAJAS:
- Para "¿cuánto/cuántas/cuándo?" usa las herramientas de datos.
- Para "¿por qué/cómo funciona?" usa search_knowledge y cita el documento.
- Puedes llamar a varias herramientas antes de responder.
- Si search_knowledge no devuelve nada, di que no consta en la documentación.

ESTILO: español claro y directo. Sin emojis. Sin promesas de rentabilidad. Honesto sobre
lo que el sistema NO ha demostrado. Cita la fuente de cada dato entre paréntesis."""

MAX_TOOL_ROUNDS = 5


@dataclass
class AssistantAnswer:
    text: str
    tools_used: list[str] = field(default_factory=list)
    rounds: int = 0


class AssistantError(RuntimeError):
    """El asistente no pudo producir una respuesta."""


class AssistantService:
    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    @property
    def client(self) -> Any:
        return self._client or get_groq_client()

    async def ask(self, question: str) -> AssistantAnswer:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        tools_used: list[str] = []

        for round_number in range(1, MAX_TOOL_ROUNDS + 1):
            message = await self._complete(messages)

            calls = getattr(message, "tool_calls", None)
            if not calls:
                text = (message.content or "").strip()
                if text:
                    return AssistantAnswer(
                        text=text, tools_used=tools_used, rounds=round_number
                    )
                # Los modelos de razonamiento a veces terminan con `content=None`
                # y todo en su razonamiento interno, que NO debe mostrarse al
                # usuario: es deliberación en bruto, no una respuesta. Se pide
                # una respuesta explícita en vez de fallar.
                return AssistantAnswer(
                    text=await self._force_answer(messages),
                    tools_used=tools_used,
                    rounds=round_number + 1,
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in calls
                    ],
                }
            )

            for call in calls:
                name = call.function.name
                tools_used.append(name)
                result = await self._run_tool(name, call.function.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": name,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

        # Agotadas las rondas, se fuerza una respuesta en vez de fallar. Lo
        # descubrió una prueba real: ante "¿subirá BTC mañana? ¿meto más dinero?"
        # el modelo encadenaba consultas buscando una respuesta que no existe.
        # Es justo la pregunta que MÁS importa que conteste, porque la respuesta
        # correcta es negarse.
        return AssistantAnswer(
            text=await self._force_answer(messages),
            tools_used=tools_used,
            rounds=MAX_TOOL_ROUNDS + 1,
        )

    async def _force_answer(self, messages: list[dict[str, Any]]) -> str:
        """Pide una respuesta en texto plano, sin herramientas disponibles."""
        nudged = messages + [
            {
                "role": "user",
                "content": (
                    "Responde ahora en texto plano con lo que sepas. Si la pregunta "
                    "pide una predicción de precio o consejo de inversión, di "
                    "claramente que no puedes hacerlo y explica por qué."
                ),
            }
        ]

        message = await self._complete(nudged, use_tools=False)
        text = (message.content or "").strip()
        if not text:
            raise AssistantError("El asistente no produjo ninguna respuesta.")
        return text

    async def _complete(
        self, messages: list[dict[str, Any]], *, use_tools: bool = True
    ) -> Any:
        def call() -> Any:
            kwargs: dict[str, Any] = {
                "model": settings.groq_model,
                "temperature": 0,
                "messages": messages,
            }
            if use_tools:
                kwargs["tools"] = tool_specs()
                kwargs["tool_choice"] = "auto"
            return self.client.chat.completions.create(**kwargs)

        response = await asyncio.to_thread(call)
        return response.choices[0].message

    @staticmethod
    async def _run_tool(name: str, raw_arguments: str) -> dict[str, Any]:
        """
        Ejecuta una herramienta. Los fallos se devuelven al modelo como dato, no
        se lanzan: así puede decir "no pude consultarlo" en vez de romperse.
        """
        function = get_callable(name)
        if function is None:
            return {"error": f"Herramienta desconocida: {name}"}

        try:
            arguments = json.loads(raw_arguments) if raw_arguments else {}
        except json.JSONDecodeError:
            return {"error": "Argumentos inválidos."}

        try:
            return await function(**arguments)
        except TypeError as exc:
            return {"error": f"Argumentos incorrectos para {name}: {exc}"}
        except Exception as exc:  # noqa: BLE001 - el modelo debe poder explicarlo
            logger.exception("Fallo ejecutando la herramienta %s", name)
            return {"error": f"La consulta falló: {type(exc).__name__}"}
