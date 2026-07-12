"""
Business logic for the AI Trip Planner. Builds a structured prompt from
the request + (eventually) the user's learned preferences, asks Gemini for
strict JSON matching our itinerary shape, then persists it via TripRepository.

This is the seed of the "Hybrid Recommendation Engine" / "Explainable AI"
requirements from the master prompt: the `reasoning` field the model is
asked to fill in per activity is surfaced to the frontend as the
"why we suggested this" explanation. Confidence scoring and preference
learning are follow-up iterations, not implemented yet.
"""
from __future__ import annotations

from app.core.gemini import generate_json
from app.repositories.trip_repository import TripRepository
from app.schemas.trip import GenerateItineraryRequest, TripResponse

SYSTEM_PROMPT = """You are an expert travel planner. Given a destination, date \
range, budget, currency, travel style, and interests, produce a day-by-day \
itinerary. Respond with ONLY a JSON object of this exact shape, no prose:

{
  "days": [
    {
      "day_number": 1,
      "title": "string",
      "activities": [
        {
          "time": "e.g. 09:00 AM",
          "title": "string",
          "description": "1-2 sentences",
          "location": "string",
          "estimated_cost": 0.0
        }
      ]
    }
  ],
  "estimated_total_cost": 0.0
}

Keep the sum of estimated_cost across all activities close to the given budget. \
Use the given currency's typical price points. Order activities by time within each day."""


class TripPlannerService:
    def __init__(self, trip_repository: TripRepository) -> None:
        self._trips = trip_repository

    async def generate_itinerary(self, user_id: str, request: GenerateItineraryRequest) -> TripResponse:
        num_days = (request.end_date - request.start_date).days + 1
        user_prompt = (
            f"Destination: {request.destination}\n"
            f"Trip length: {num_days} days ({request.start_date} to {request.end_date})\n"
            f"Budget: {request.budget} {request.currency}\n"
            f"Travel style: {request.travel_style}\n"
            f"Interests: {', '.join(request.interests) or 'general sightseeing'}"
        )

        ai_result = await generate_json(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt)

        trip = await self._trips.create(
            {
                "user_id": user_id,
                "destination": request.destination,
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "budget": request.budget,
                "currency": request.currency,
                "travel_style": request.travel_style,
                "days": ai_result["days"],
                "estimated_total_cost": ai_result["estimated_total_cost"],
            }
        )

        return TripResponse(
            id=trip.id,
            destination=trip.destination,
            start_date=trip.start_date,
            end_date=trip.end_date,
            budget=trip.budget,
            currency=trip.currency,
            travel_style=trip.travel_style,
            days=trip.days,
            estimated_total_cost=trip.estimated_total_cost,
            is_saved=trip.is_saved,
        )

    async def list_trips(self, user_id: str, *, saved_only: bool = False) -> list[TripResponse]:
        trips = await self._trips.list_for_user(user_id, saved_only=saved_only)
        return [
            TripResponse(
                id=t.id,
                destination=t.destination,
                start_date=t.start_date,
                end_date=t.end_date,
                budget=t.budget,
                currency=t.currency,
                travel_style=t.travel_style,
                days=t.days,
                estimated_total_cost=t.estimated_total_cost,
                is_saved=t.is_saved,
            )
            for t in trips
        ]

    async def set_saved(self, trip_id: str, is_saved: bool) -> None:
        await self._trips.set_saved(trip_id, is_saved)

    async def delete_trip(self, trip_id: str) -> None:
        await self._trips.delete(trip_id)
