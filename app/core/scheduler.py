"""Scheduled deterministic signal capture for educational paper trading."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.bot.telegram_bot import send_signal_alert
from app.config import settings
from app.services.signal_service import SignalService
from app.services.tracker_service import TrackerService

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def capture_signal_job() -> None:
    """Generate and persist one signal for the configured default symbol."""
    try:
        tracking = await TrackerService().evaluate_pending()
        _, stored = await SignalService().generate_and_store(settings.default_symbol)
        if stored is not None:
            logger.info(
                "Signal captured: %s %s @ %s",
                stored.action,
                stored.pair,
                stored.signal_timestamp,
            )
            await send_signal_alert(stored)
        else:
            logger.info("Signal for this candle already exists.")
        logger.info(
            "Tracking run: scanned=%d eligible=%d created=%d skipped_existing=%d",
            tracking.scanned,
            tracking.eligible,
            tracking.created,
            tracking.skipped_existing,
        )
    except Exception:  # noqa: BLE001 - a scheduled job must not stop the scheduler
        logger.exception("Error capturing scheduled signal.")


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
    logger.info("Scheduler started (cron='%s').", settings.scheduler_cron)


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
