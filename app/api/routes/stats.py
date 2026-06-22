from fastapi import APIRouter, HTTPException, Query

from app.schemas.regime import SignalStatsRead, TrackingRunRead
from app.services.market_data import MarketDataError
from app.services.tracker_service import TrackerService

router = APIRouter(tags=["tracking"])


@router.post("/tracking/evaluate", response_model=TrackingRunRead)
async def evaluate_pending_signals(
    limit: int = Query(default=500, ge=1, le=1000),
) -> TrackingRunRead:
    try:
        return await TrackerService().evaluate_pending(limit)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/stats", response_model=SignalStatsRead)
async def get_signal_stats() -> SignalStatsRead:
    return await TrackerService().get_stats()
