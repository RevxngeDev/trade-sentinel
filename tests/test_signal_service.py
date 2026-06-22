from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import Base
from app.models.signal import Signal
from app.schemas.regime import RegimeConditions, RegimeIndicators, RegimeResponse
from app.services.signal_service import SignalService


def _make_response(timestamp: datetime, action: str = "BUY") -> RegimeResponse:
    return RegimeResponse(
        symbol="BTC/USDT",
        timeframe="4h",
        action=action,
        regime_on=action != "CASH",
        previous_regime_on=False,
        confidence=80,
        price=50000.0,
        timestamp=timestamp,
        decision_timestamp=timestamp - timedelta(hours=4),
        indicators=RegimeIndicators(close=50000, ema_50=49000, ema_200=48000, rsi_14=55),
        conditions=RegimeConditions(
            close_above_ema50=True,
            close_above_ema200=True,
            ema50_above_ema200=True,
            ema50_rising=True,
            ema200_rising=True,
            rsi_above_50=True,
        ),
        reasoning="test",
        warning="test",
    )


@pytest_asyncio.fixture
async def session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session

    await engine.dispose()


async def _count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Signal))


async def test_persist_creates_signal(session):
    service = SignalService()
    ts = datetime(2026, 6, 11, 16, 0, tzinfo=timezone.utc)

    stored = await service.persist(session, _make_response(ts))

    assert stored is not None
    assert stored.id is not None
    assert stored.pair == "BTC/USDT"
    assert stored.action == "BUY"
    assert stored.conditions["rsi_above_50"] is True
    assert await _count(session) == 1


async def test_persist_dedupes_same_candle(session):
    service = SignalService()
    ts = datetime(2026, 6, 11, 16, 0, tzinfo=timezone.utc)

    first = await service.persist(session, _make_response(ts))
    second = await service.persist(session, _make_response(ts, action="HOLD"))

    assert first is not None
    assert second is None  # mismo (par, vela) -> no se duplica
    assert await _count(session) == 1


async def test_persist_distinct_candles(session):
    service = SignalService()
    ts = datetime(2026, 6, 11, 16, 0, tzinfo=timezone.utc)

    await service.persist(session, _make_response(ts))
    await service.persist(session, _make_response(ts + timedelta(hours=1)))

    assert await _count(session) == 2
