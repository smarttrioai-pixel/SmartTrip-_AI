from datetime import date

from pydantic import BaseModel, Field


class GenerateItineraryRequest(BaseModel):
    destination: str = Field(..., min_length=2)
    start_date: date
    end_date: date
    budget: float = Field(..., gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    travel_style: str = Field(default="balanced")  # e.g. relaxed, adventure, luxury, budget
    interests: list[str] = Field(default_factory=list)


class ExplanationResponse(BaseModel):
    reason_text: str
    budget_match: float
    interest_match: float
    context_score: float
    confidence: float


class Activity(BaseModel):
    time: str
    title: str
    description: str
    location: str
    estimated_cost: float
    explanation: ExplanationResponse | None = None


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


class SaveTripRequest(BaseModel):
    is_saved: bool = True
