from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, get_memory_engine
from app.cognitive.memory_engine import MemoryEngine
from app.schemas.memory import (
    InferredPreferenceResponse,
    MemoryInsightsResponse,
    PreferenceSummaryResponse,
    SavePreferenceRequest,
)

router = APIRouter(prefix="/memory", tags=["Memory"])


@router.get("/insights", response_model=MemoryInsightsResponse)
async def get_insights(
    current_user: CurrentUser,
    memory_engine: Annotated[MemoryEngine, Depends(get_memory_engine)],
) -> MemoryInsightsResponse:
    insights = await memory_engine.get_insights(current_user.id)
    return MemoryInsightsResponse(
        preferences=[
            PreferenceSummaryResponse(
                id=p.id, source_text=p.source_text, source_type=p.source_type, weight=p.weight
            )
            for p in insights["preferences"]
        ],
        inferred_preferences=[
            InferredPreferenceResponse(
                id=p.id,
                statement=p.statement,
                confidence=p.confidence,
                supporting_event_count=p.supporting_event_count,
                status=p.status,
            )
            for p in insights["inferred_preferences"]
        ],
        feature_weights=insights["feature_weights"],
    )


@router.post("/preferences", status_code=status.HTTP_201_CREATED)
async def save_preference(
    payload: SavePreferenceRequest,
    current_user: CurrentUser,
    memory_engine: Annotated[MemoryEngine, Depends(get_memory_engine)],
) -> dict[str, str]:
    await memory_engine.save_preference(current_user.id, payload.source_text, payload.source_type)
    return {"message": "Preference saved."}


@router.post("/inferences/{inference_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_inference(
    inference_id: str,
    current_user: CurrentUser,
    memory_engine: Annotated[MemoryEngine, Depends(get_memory_engine)],
) -> None:
    await memory_engine.reject_inference(current_user.id, inference_id)
