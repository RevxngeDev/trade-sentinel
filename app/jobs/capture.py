"""
Entry point para la captura programada de señales (p.ej. cron de GitHub Actions).

Hace lo mismo que el scheduler en proceso, pero stateless (corre y termina), por
lo que funciona en un runner de cron sin servidor encendido 24/7:

1. Backfill de las fronteras 4h que falten (idempotente).
2. `capture_signal_job`: evalúa pendientes, captura la señal actual y envía la
   alerta de Telegram cuando se guarda una señal nueva.

Uso: `python -m app.jobs.capture`
"""

from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.core.scheduler import capture_signal_job
from app.services.signal_service import SignalService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run() -> None:
    result = await SignalService().backfill(settings.default_symbol)
    logger.info(
        "Backfill: scanned=%d created=%d skipped_existing=%d skipped_insufficient=%d",
        result.scanned,
        result.created,
        result.skipped_existing,
        result.skipped_insufficient,
    )
    await capture_signal_job()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
