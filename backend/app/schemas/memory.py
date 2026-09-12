from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class InferredPreferenceResponse(BaseModel):
    id: str
    statement: str
    confidence: float
    supporting_event_count: int
    status: str


class PreferenceSummaryResponse(BaseModel):
    id: str
    source_text: str
    source_type: str
    weight: float


class MemoryInsightsResponse(BaseModel):
    preferences: list[PreferenceSummaryResponse]
    inferred_preferences: list[InferredPreferenceResponse]
    feature_weights: dict[str, float]


class SavePreferenceRequest(BaseModel):
    source_text: str = Field(..., min_length=2, max_length=1000)
    source_type: str = Field(default="explicit_interest")


class RecordEventRequest(BaseModel):
    recommendation_id: str
    event_type: str = Field(..., pattern="^(accept|reject|edit)$")
    # Which behavioral features this recommendation touches and in which
    # direction, e.g. {"distance_tolerance": -1, "budget_sensitivity": 0.5}.
    # Populated by the caller (trip_service today, Recommendation Engine
    # from Phase 4 onward) based on the recommendation's own attributes.
    feature_deltas: dict[str, float] = Field(default_factory=dict)


class ActivityFeedbackRequest(BaseModel):
    """
    Per-activity feedback from the user.

    This is the primary mechanism for adaptive learning — it directly
    calls MemoryEngine.record_activity_event() which:
    1. Resolves feature_deltas from category + rejection_reason
    2. Updates behavioral feature_weights in memory_behavioral/{uid}
    3. Persists a feedback document to memory_feedback collection
    4. Triggers run_promotion() for InferredPreference promotion
    """
    trip_id: str = Field(..., description="The trip this activity belongs to")
    activity_title: str = Field(..., min_length=1, max_length=500)
    activity_category: str = Field(
        default="other",
        description="Activity category from Qwen: attraction|culture|nature|museum|meal|transport|other",
    )
    event_type: Literal["accept", "reject", "edit"] = Field(
        ...,
        description="accept = user liked it, reject = user disliked it, edit = user modified it",
    )
    rejection_reason: Literal[
        "too_expensive", "too_crowded", "too_far",
        "not_interested", "already_visited", "wrong_type", "other"
    ] | None = Field(
        default=None,
        description="Required when event_type=reject. Drives feature_delta computation.",
    )
    rating: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Optional 1–5 star rating",
    )
    free_text: str | None = Field(
        default=None,
        max_length=500,
        description="Optional free-text comment",
    )


class ActivityFeedbackResponse(BaseModel):
    """Response after recording activity feedback."""
    message: str
    feature_deltas_applied: dict[str, float]
    updated_feature_weights: dict[str, float]
    new_inferred_preferences: list[str]
