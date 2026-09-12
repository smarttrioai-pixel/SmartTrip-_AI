"""
Memory API routes for SmartTrip AI.

Phase 4 (Feedback loop added):
  POST /memory/feedback — NEW: per-activity user feedback endpoint.
    This is the primary mechanism for adaptive learning.
    Calling this route directly updates behavioral feature_weights in
    memory_behavioral/{uid} (Firestore) and persists a FeedbackMemory
    document to memory_feedback/{auto-id}.

    Causal chain:
        User clicks 👎 'Too expensive' on an activity
        → POST /memory/feedback {event_type: 'reject', rejection_reason: 'too_expensive'}
        → _resolve_feature_deltas() → {budget_sensitivity: -1.0}
        → MemoryEngine.record_event() → memory_behavioral/{uid}.feature_weights updated
        → MemoryRepository.add_feedback() → memory_feedback/{id} written
        → MemoryEngine.run_promotion() → InferredPreference may be promoted
        → Next trip generation: feature_weights influence Qwen prompt AND
          personalization_score in RecommendationEngine
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, get_memory_engine
from app.cognitive.memory_engine import MemoryEngine, _resolve_feature_deltas
from app.schemas.memory import (
    ActivityFeedbackRequest,
    ActivityFeedbackResponse,
    InferredPreferenceResponse,
    MemoryInsightsResponse,
    PreferenceSummaryResponse,
    SavePreferenceRequest,
)

router = APIRouter(prefix="/memory", tags=["Memory"])
logger = logging.getLogger(__name__)


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


@router.post("/inferences/{inference_id}/reject", status_code=status.HTTP_200_OK)
async def reject_inference(
    inference_id: str,
    current_user: CurrentUser,
    memory_engine: Annotated[MemoryEngine, Depends(get_memory_engine)],
) -> None:
    await memory_engine.reject_inference(current_user.id, inference_id)


@router.post(
    "/feedback",
    response_model=ActivityFeedbackResponse,
    status_code=status.HTTP_200_OK,
    summary="Record per-activity user feedback (accept/reject/edit)",
    description=(
        "Records user feedback on a recommended activity. "
        "Directly updates behavioral memory feature_weights in Firestore, "
        "persists a feedback document to memory_feedback, and triggers "
        "InferredPreference promotion. "
        "This is the primary mechanism for adaptive learning in SmartTrip AI."
    ),
)
async def record_activity_feedback(
    payload: ActivityFeedbackRequest,
    current_user: CurrentUser,
    memory_engine: Annotated[MemoryEngine, Depends(get_memory_engine)],
) -> ActivityFeedbackResponse:
    """Record per-activity user feedback and update behavioral memory."""
    if payload.event_type == "reject" and payload.rejection_reason is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rejection_reason is required when event_type is 'reject'.",
        )

    # Resolve deltas upfront so we can include them in the response
    feature_deltas = _resolve_feature_deltas(
        payload.activity_category,
        payload.event_type,
        payload.rejection_reason,
    )

    try:
        await memory_engine.record_activity_event(
            user_id=current_user.id,
            trip_id=payload.trip_id,
            activity_title=payload.activity_title,
            activity_category=payload.activity_category,
            event_type=payload.event_type,
            rejection_reason=payload.rejection_reason,
            rating=payload.rating,
            free_text=payload.free_text,
        )
    except Exception as exc:
        logger.error(
            "FEEDBACK_RECORD_ERROR user_id=%s trip_id=%s event_type=%s error=%s",
            current_user.id, payload.trip_id, payload.event_type, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record feedback. Please try again.",
        ) from exc

    # Return current state so frontend can display confirmation + updated weights
    insights = await memory_engine.get_insights(current_user.id)
    new_inferred = [p.statement for p in insights["inferred_preferences"]]

    logger.info(
        "FEEDBACK_RECORDED user_id=%s trip_id=%s event=%s reason=%s deltas=%s",
        current_user.id, payload.trip_id, payload.event_type,
        payload.rejection_reason, feature_deltas,
    )

    return ActivityFeedbackResponse(
        message=(
            f"Feedback recorded: {payload.event_type}"
            + (f" ({payload.rejection_reason})" if payload.rejection_reason else "")
        ),
        feature_deltas_applied=feature_deltas,
        updated_feature_weights=insights["feature_weights"],
        new_inferred_preferences=new_inferred,
    )
