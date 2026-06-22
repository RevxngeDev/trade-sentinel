from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.regime import RegimeResponse
from app.services.market_data import MarketDataError
from app.services.signal_service import SignalService


router = APIRouter(prefix="/regime", tags=["regime"])


@router.get("/{symbol}", response_model=RegimeResponse)
async def get_regime_signal(symbol: str) -> RegimeResponse:
    try:
        return await SignalService().generate(symbol)

    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error while analyzing regime: {exc}",
        ) from exc
