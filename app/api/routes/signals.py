from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.regime import BackfillRunRead, SignalRead
from app.services.market_data import MarketDataError, MarketDataService
from app.services.signal_service import SignalService

router = APIRouter(prefix="/signals", tags=["signals"])


@router.post("/backfill/{symbol}", response_model=BackfillRunRead)
async def backfill_signals(symbol: str) -> BackfillRunRead:
    """Rellena las señales de fronteras 4h que falten (idempotente)."""
    try:
        return await SignalService().backfill(symbol)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[SignalRead])
async def list_signals(
    pair: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[SignalRead]:
    normalized_pair = MarketDataService.normalize_symbol(pair) if pair else None
    return await SignalService().list_signals(normalized_pair, limit)


@router.post("/{symbol}", response_model=SignalRead)
async def capture_signal(symbol: str) -> SignalRead:
    service = SignalService()

    try:
        response, stored = await service.generate_and_store(symbol)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if stored is not None:
        return stored

    existing = await service.get_by_candle(response.symbol, response.timestamp)
    if existing is None:
        raise HTTPException(status_code=500, detail="Could not retrieve the signal.")
    return existing
