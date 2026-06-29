import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.interpretations import router as interpretations_router
from app.api.routes.regime import router as regime_router
from app.api.routes.signals import router as signals_router
from app.api.routes.stats import router as stats_router
from app.bot.telegram_bot import telegram_bot
from app.config import settings
from app.core.scheduler import shutdown_scheduler, start_scheduler
from app.services.signal_service import SignalService
from app.services.tracker_service import TrackerService

logger = logging.getLogger(__name__)

# Mantiene referencia a la tarea de arranque para que no la recoja el GC.
_background_tasks: set[asyncio.Task] = set()


async def _startup_catch_up() -> None:
    """Rellena huecos de captura (apagones) y evalúa pendientes. No fatal."""
    try:
        result = await SignalService().backfill(settings.default_symbol)
        logger.info(
            "Backfill: scanned=%d created=%d skipped_existing=%d skipped_insufficient=%d",
            result.scanned,
            result.created,
            result.skipped_existing,
            result.skipped_insufficient,
        )
        tracking = await TrackerService().evaluate_pending()
        logger.info(
            "Startup tracking: eligible=%d created=%d",
            tracking.eligible,
            tracking.created,
        )
    except Exception:  # noqa: BLE001 - el catch-up no debe impedir el arranque
        logger.exception("Startup catch-up failed (non-fatal).")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.telegram_enabled:
        await telegram_bot.start()

    if settings.backfill_on_startup:
        task = asyncio.create_task(_startup_catch_up())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    if settings.scheduler_enabled:
        start_scheduler()

    yield

    if settings.scheduler_enabled:
        shutdown_scheduler()

    if settings.telegram_enabled:
        await telegram_bot.stop()


app = FastAPI(
    title=settings.project_name,
    version="0.1.0",
    description="TradeSentinel MVP - BTC regime agent for educational paper trading.",
    lifespan=lifespan,
)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "app": settings.project_name,
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(regime_router)
app.include_router(signals_router)
app.include_router(stats_router)
app.include_router(interpretations_router)
app.include_router(dashboard_router)
