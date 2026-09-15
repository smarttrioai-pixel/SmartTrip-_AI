from datetime import date

from pydantic import BaseModel, Field


class GenerateItineraryRequest(BaseModel):
    destination: str = Field(..., min_length=2)
    start_date: date
    end_date: date
    budget: float = Field(..., gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    travel_style: str = Field(default="balanced")
    interests: list[str] = Field(default_factory=list)
    # "any" means the planner must not assume flight/train/bus/car.
    transport: str = Field(default="any")


class ExplanationResponse(BaseModel):
    reason_text: str
    budget_match: float
    interest_match: float
    weather_match: float
    context_score: float
    confidence: float
    # Added Phase 4: personalization score from behavioral memory.
    # None for trips generated before this field was added (backward compatible).
    personalization_score: float | None = None
    unavailable_factors: list[str] = Field(default_factory=list)



class ActivityAlternative(BaseModel):
    place_id: str
    title: str
    description: str
    category: str
    location: str
    lat: float | None = None
    lon: float | None = None
    distance_meters: int | None = None
    estimated_cost: float = 0.0
    duration_minutes: int | None = None
    opening_status: str | None = None
    rating: float | None = None
    reason: str = ""   # OpenAI-generated explanation
    preference_match: float | None = None  # 0.0-1.0


class Activity(BaseModel):
    id: str | None = None               # uuid4, generated on creation
    time: str
    title: str
    description: str
    location: str
    estimated_cost: float
    category: str | None = None
    reason: str | None = None
    meal_type: str | None = None
    food_query: str | None = None
    explanation: ExplanationResponse | None = None
    place_enrichment: dict | None = None
    scif_rejected: bool | None = None
    scif_rejection_reason: str | None = None
    # Google Places fields (optional, backward-compatible)
    place_id: str | None = None              # Google place_id
    rating: float | None = None              # 0–5 Google rating
    user_ratings_total: int | None = None    # Google review count
    place_types: list[str] | None = None     # Google types list
    verified: bool | None = None             # Verified by places provider
    place_provider: str | None = None        # "google" | "geoapify"
    # Slot intent from Qwen (before enrichment overwrites title)
    slot_intent: str | None = None
    # Description correction metadata
    description_corrected: bool | None = None
    duration_minutes: int | None = None
    travel_time_minutes: int | None = None
    travel_mode: str | None = None      # walk|drive|transit
    booking_required: bool = False
    weather_suitability: str | None = None  # good|fair|poor
    liked: bool | None = None
    disliked: bool | None = None
    user_feedback: str | None = None
    alternatives: list['ActivityAlternative'] | None = None


class DayPlanResponse(BaseModel):
    day_number: int
    title: str
    activities: list[Activity]


class TripResponse(BaseModel):
    id: str
    destination: str
    start_date: str
    end_date: str
    budget: float
    currency: str
    travel_style: str
    days: list[DayPlanResponse]
    estimated_total_cost: float
    is_saved: bool
    # Cognitive trace: non-sensitive summary of SCIF decisions and live context.
    # Null for trips generated before this feature was added (backward compatible).
    cognitive_trace: dict | None = None


class SaveTripRequest(BaseModel):
    is_saved: bool = True


class ModifyItineraryRequest(BaseModel):
    """User's natural-language modification request."""
    user_message: str = Field(..., min_length=1)

class ModifyItineraryResponse(BaseModel):
    """Result of applying a modification to the itinerary."""
    success: bool
    message: str
    updated_trip: 'TripResponse | None' = None
    conflict: str | None = None  # schedule conflict description if any

class AlternativesRequest(BaseModel):
    activity_id: str
    day_number: int

class AlternativesResponse(BaseModel):
    activity_id: str
    alternatives: list[ActivityAlternative]

class ReplaceActivityRequest(BaseModel):
    activity_id: str
    day_number: int
    place_id: str            # Google place_id of chosen alternative
    alternative_title: str   # Human-readable confirmation

class MoveActivityRequest(BaseModel):
    activity_id: str
    from_day: int
    to_day: int
    new_time: str            # e.g. "14:00"

class ReorderRequest(BaseModel):
    day_number: int
    ordered_activity_ids: list[str]  # new order of activity ids
