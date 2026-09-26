"""
Herramientas de SOLO LECTURA que el asistente puede invocar.

Principio: **el LLM nunca calcula un número**. Cada cifra de una respuesta sale de
una de estas funciones, que a su vez leen Supabase o reutilizan los servicios ya
validados (`TrackerService`, `compute_equity`). El modelo solo decide qué
herramienta pedir y cómo redactar el resultado.

Separación deliberada de fuentes:
- Preguntas de "cuánto / cuándo / cuántas" -> estas herramientas (datos en vivo).
- Preguntas de "por qué / cómo" -> `search_knowledge` (documentos del proyecto).

Los documentos NO son fuente de números: un documento escrito hace días daría una
cifra caducada con cara de actual.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Awaitable, Callable

from app.config import settings
from app.services.knowledge_service import KnowledgeService
from app.services.signal_service import SignalService
from app.services.signal_store import SupabaseAIOpinionStore
from app.services.tracker_service import TrackerService

# Límite de señales a leer para reconstruir historia. 2000 cubre ~9 meses a la
# cadencia actual (~8/día).
HISTORY_LIMIT = 2000


async def get_performance() -> dict[str, Any]:
    """Rendimiento real reconstruido (con fees) frente a comprar y mantener."""
    performance = await TrackerService().get_performance()
    return {
        "estrategia_pct": performance.strategy_return_pct,
        "buy_and_hold_pct": performance.benchmark_return_pct,
        "diferencia_pp": performance.difference_pp,
        "exposicion_pct": performance.exposure_pct,
        "max_drawdown_pct": performance.max_drawdown_pct,
        "operaciones_cerradas_y_abiertas": performance.round_trips,
        "equity_inicial": performance.initial_equity,
        "equity_final": performance.final_strategy_equity,
        "nota": "Equity reconstruida desde las señales guardadas, fees 0.1%.",
    }


async def get_signal_stats() -> dict[str, Any]:
    """Recuento de señales y resultados del seguimiento."""
    stats = await TrackerService().get_stats()
    return {
        "señales_totales": stats.total_signals,
        "evaluadas": stats.evaluated_signals,
        "pendientes": stats.pending_signals,
        "señales_en_posicion": stats.active_signals,
        "señales_en_efectivo": stats.cash_signals,
        "acierto_en_posicion_pct": stats.active_win_rate_pct,
        "retorno_medio_en_posicion_pct": stats.average_active_return_pct,
        "horizonte_horas": stats.tracking_horizon_hours,
        "nota": (
            "Son observaciones forward por señal, NO el rendimiento de la cartera. "
            "Para el rendimiento real usa get_performance."
        ),
    }


async def get_latest_signal() -> dict[str, Any]:
    """Última señal determinista guardada."""
    signals = await SignalService().list_signals(settings.default_symbol, 1)
    if not signals:
        return {"error": "No hay señales guardadas."}

    signal = signals[0]
    return {
        "par": signal.pair,
        "accion": signal.action,
        "precio": signal.price,
        "momento_utc": signal.signal_timestamp.isoformat(),
        "regimen_activo": signal.regime_on,
        "razonamiento": signal.reasoning,
    }


async def get_trade_history() -> dict[str, Any]:
    """Operaciones completas: entradas, salidas y retorno bruto de cada una."""
    signals = await SignalService().list_signals(settings.default_symbol, HISTORY_LIMIT)
    ordered = sorted(signals, key=lambda s: s.signal_timestamp)

    trades: list[dict[str, Any]] = []
    entry = None

    for signal in ordered:
        in_position = signal.action != "CASH"
        if in_position and entry is None:
            entry = signal
        elif not in_position and entry is not None:
            trades.append(_trade(entry, signal, closed=True))
            entry = None

    if entry is not None and ordered:
        trades.append(_trade(entry, ordered[-1], closed=False))

    return {
        "operaciones": trades,
        "total": len(trades),
        "nota": "Retorno BRUTO entre precios de apertura, sin fees.",
    }


def _trade(entry, exit_signal, *, closed: bool) -> dict[str, Any]:
    gross = (float(exit_signal.price) / float(entry.price) - 1) * 100
    hours = (
        exit_signal.signal_timestamp - entry.signal_timestamp
    ).total_seconds() / 3600
    return {
        "entrada_utc": entry.signal_timestamp.isoformat(),
        "precio_entrada": entry.price,
        "salida_utc": exit_signal.signal_timestamp.isoformat(),
        "precio_salida": exit_signal.price,
        "retorno_bruto_pct": round(gross, 2),
        "duracion_horas": round(hours),
        "cerrada": closed,
    }


async def get_ai_opinion_stats() -> dict[str, Any]:
    """Fiabilidad del registro de opiniones del LLM (calibración futura)."""
    opinions = await SupabaseAIOpinionStore().list_opinions(500)
    if not opinions:
        return {"total": 0, "nota": "Aún no hay opiniones registradas."}

    statuses = Counter(opinion.status for opinion in opinions)
    confidences = [o.confidence for o in opinions if o.confidence is not None]

    return {
        "total": len(opinions),
        "por_estado": dict(statuses),
        "confianza_n": len(confidences),
        "confianza_media": (
            round(sum(confidences) / len(confidences), 1) if confidences else None
        ),
        "confianza_distribucion": dict(sorted(Counter(confidences).items())),
        "nota": (
            "La IA NO decide: estas opiniones se registran sin afectar a la señal, "
            "para medir algún día si aportan."
        ),
    }


async def search_knowledge(query: str) -> dict[str, Any]:
    """Busca en los documentos del proyecto (decisiones, research, arquitectura)."""
    service = KnowledgeService()
    chunks = await service.search(query, limit=4)

    if not chunks:
        return {
            "resultados": [],
            "nota": "Sin coincidencias. No inventes la respuesta: di que no consta.",
        }

    return {
        "resultados": [
            {
                "fuente": chunk.source,
                "seccion": chunk.section,
                "contenido": chunk.content,
                "ingestado_utc": chunk.ingested_at.isoformat(),
            }
            for chunk in chunks
        ]
    }


async def get_knowledge_freshness() -> dict[str, Any]:
    """Cuándo se ingestó cada documento. El asistente debe declarar esta fecha."""
    service = KnowledgeService()
    entries = await service.freshness()
    age = await service.knowledge_age_days()

    return {
        "documentos": [
            {
                "fuente": entry.source,
                "fragmentos": entry.chunks,
                "ingestado_utc": entry.ingested_at.isoformat(),
            }
            for entry in entries
        ],
        "antiguedad_maxima_dias": None if age is None else round(age, 1),
        "nota": (
            "La ingesta es manual. Si la antigüedad es alta, avisa al usuario de que "
            "el conocimiento documental puede estar desactualizado."
        ),
    }


# Catálogo: descripción para el modelo + función a ejecutar.
TOOLS: dict[str, dict[str, Any]] = {
    "get_performance": {
        "fn": get_performance,
        "description": (
            "Rendimiento REAL del paper trading frente a comprar y mantener, con fees. "
            "Úsala para '¿cómo voy?', '¿gano o pierdo?', '¿bato al mercado?'."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "get_signal_stats": {
        "fn": get_signal_stats,
        "description": (
            "Recuento de señales, evaluadas y pendientes, y tasa de acierto por señal."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "get_latest_signal": {
        "fn": get_latest_signal,
        "description": "Última señal guardada: acción actual, precio y momento.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "get_trade_history": {
        "fn": get_trade_history,
        "description": (
            "Lista de operaciones con entrada, salida, retorno y duración. "
            "Úsala para '¿cuántas operaciones?', '¿cuál fue la mejor?'."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "get_ai_opinion_stats": {
        "fn": get_ai_opinion_stats,
        "description": "Estadísticas del registro de opiniones del LLM y su fiabilidad.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "search_knowledge": {
        "fn": search_knowledge,
        "description": (
            "Busca en la documentación del proyecto: por qué se tomó una decisión, qué "
            "se descartó y por qué, cómo funciona el sistema, qué dijo un research. "
            "Úsala SIEMPRE para preguntas de '¿por qué...?' o '¿cómo funciona...?'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Palabras clave en español, p.ej. 'apalancamiento vol-targeting'.",
                }
            },
            "required": ["query"],
        },
    },
    "get_knowledge_freshness": {
        "fn": get_knowledge_freshness,
        "description": "Fecha de ingesta de cada documento del proyecto.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def tool_specs() -> list[dict[str, Any]]:
    """Catálogo en el formato de function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }
        for name, tool in TOOLS.items()
    ]


def get_callable(name: str) -> Callable[..., Awaitable[dict[str, Any]]] | None:
    tool = TOOLS.get(name)
    return tool["fn"] if tool else None
