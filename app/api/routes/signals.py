from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.signal import Signal
from app.schemas.regime import SignalRead
from app.services.market_data import MarketDataError, MarketDataService
from app.services.signal_service import SignalService

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=list[SignalRead])
async def list_signals(
    pair: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[Signal]:
    stmt = select(Signal).order_by(Signal.signal_timestamp.desc()).limit(limit)

    if pair:
        stmt = stmt.where(Signal.pair == MarketDataService.normalize_symbol(pair))

    result = await session.scalars(stmt)
    return list(result)


@router.post("/{symbol}", response_model=SignalRead)
async def capture_signal(
    symbol: str,
    session: AsyncSession = Depends(get_session),
) -> Signal:
    service = SignalService()

    try:
        response, stored = await service.generate_and_store(session, symbol)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if stored is not None:
        return stored

    # Ya existía una señal para esa vela: devolvemos la guardada.
    existing = await session.scalar(
        select(Signal).where(
            Signal.pair == response.symbol,
            Signal.signal_timestamp == response.timestamp,
        )
    )
    if existing is None:
        raise HTTPException(status_code=500, detail="No se pudo recuperar la señal.")
    return existing
