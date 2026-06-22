"""
Scheduler de captura de señales para paper trading 24/7.

Cada cierre de vela 4h dispara la generación + persistencia de la señal del
símbolo por defecto. Desactivado salvo que `scheduler_enabled` sea True.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.core.database import async_session_factory
from app.services.signal_service import SignalService

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def capture_signal_job() -> None:
    """Genera y persiste la señal del símbolo por defecto."""
    try:
        async with async_session_factory() as session:
            service = SignalService()
            _, stored = await service.generate_and_store(
                session, settings.default_symbol
            )

        if stored is not None:
            logger.info(
                "Señal capturada: %s %s @ %s",
                stored.action,
                stored.pair,
                stored.signal_timestamp,
            )
        else:
            logger.info("La señal de esta vela ya estaba registrada.")
    except Exception:  # noqa: BLE001 — el job no debe tumbar el scheduler
        logger.exception("Error capturando la señal programada.")


def start_scheduler() -> None:
    if scheduler.running:
        return

    scheduler.add_job(
        capture_signal_job,
        CronTrigger.from_crontab(settings.scheduler_cron, timezone="UTC"),
        id="capture_signal",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler iniciado (cron='%s').", settings.scheduler_cron)


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
