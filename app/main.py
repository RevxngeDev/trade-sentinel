from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.interpretations import router as interpretations_router
from app.api.routes.regime import router as regime_router
from app.api.routes.signals import router as signals_router
from app.api.routes.stats import router as stats_router
from app.bot.telegram_bot import telegram_bot
from app.config import settings
from app.core.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.telegram_enabled:
        await telegram_bot.start()

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
