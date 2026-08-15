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
    unavailable_factors: list[str] = Field(default_factory=list)


class Activity(BaseModel):
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
