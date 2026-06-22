from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.regime import router as regime_router
from app.api.routes.signals import router as signals_router
from app.config import settings
from app.core.database import init_models
from app.core.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Asegura el esquema en dev. En producción la fuente de verdad es Alembic.
    await init_models()

    if settings.scheduler_enabled:
        start_scheduler()

    yield

    if settings.scheduler_enabled:
        shutdown_scheduler()


app = FastAPI(
    title=settings.project_name,
    version="0.1.0",
    description=(
        "TradeSentinel MVP — BTC Regime Agent for educational paper trading."
    ),
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
