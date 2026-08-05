"""
Dead-man's switch: alerta si la captura de señales se detuvo.

Lee la última señal guardada en Supabase y, si es más vieja que
`heartbeat_max_age_hours`, envía una alerta de Telegram. Corre en un workflow
SEPARADO del de captura (un vigilante independiente); si está sano, calla.

Uso: python -m app.jobs.heartbeat
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from app.bot.telegram_bot import send_text_alert
from app.config import settings
from app.services.signal_store import SupabaseSignalStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check(
    store: SupabaseSignalStore | None = None,
    alert: Callable[[str], Awaitable[None]] | None = None,
    now: datetime | None = None,
) -> str:
    """Devuelve 'ok' | 'stale' | 'empty'. Alerta si no es 'ok'."""
    store = store or SupabaseSignalStore()
    alert = alert or send_text_alert
    now = now or datetime.now(timezone.utc)

    signals = await store.list_signals(settings.default_symbol, 1)

    if not signals:
        await alert("⚠️ TradeSentinel: no hay señales guardadas. Revisa la captura.")
        return "empty"

    latest = signals[0].signal_timestamp
    age_hours = (now - latest).total_seconds() / 3600

    if age_hours > settings.heartbeat_max_age_hours:
        await alert(
            "⚠️ TradeSentinel: la captura parece DETENIDA. "
            f"Última señal hace {age_hours:.1f} h "
            f"({latest:%Y-%m-%d %H:%M} UTC). Revisa el workflow de GitHub Actions."
        )
        return "stale"

    logger.info("Heartbeat OK: última señal hace %.1f h.", age_hours)
    return "ok"


def main() -> None:
    asyncio.run(check())


if __name__ == "__main__":
    main()
