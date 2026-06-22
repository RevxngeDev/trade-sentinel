from fastapi import APIRouter, HTTPException

from app.schemas.regime import AgentInterpretation
from app.services.ai_agent import AIInterpretationError, AIInterpretationService
from app.services.signal_service import SignalService

router = APIRouter(prefix="/interpretations", tags=["ai"])


@router.post("/{signal_id}", response_model=AgentInterpretation)
async def interpret_signal(signal_id: int) -> AgentInterpretation:
    signal = await SignalService().get_by_id(signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found.")

    try:
        return await AIInterpretationService().interpret(signal)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIInterpretationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
