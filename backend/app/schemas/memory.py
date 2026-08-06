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
