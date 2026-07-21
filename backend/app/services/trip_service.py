"""
Business logic for the AI Trip Planner. Builds a structured prompt from
the request + the user's memory context, asks Gemini for strict JSON
matching our itinerary shape, then persists it via TripRepository.

Phase 3 integration point: `get_context()` is called before generation and
its rendered text is folded into the prompt; `record_event()`/
`run_promotion()` are triggered on save. Feature-delta attribution here is
a deliberately simple heuristic (comparing trip-level attributes, not
individual recommendations) - Phase 4's Recommendation Engine replaces this
with proper per-activity feature scoring once the pipeline exists. Flagging
this explicitly rather than presenting it as more sophisticated than it is.
"""
from __future__ import annotations

from app.cognitive.memory_engine import MemoryEngine
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
    def __init__(self, trip_repository: TripRepository, memory_engine: MemoryEngine) -> None:
        self._trips = trip_repository
        self._memory = memory_engine

    async def generate_itinerary(self, user_id: str, request: GenerateItineraryRequest) -> TripResponse:
        num_days = (request.end_date - request.start_date).days + 1
        user_prompt = (
            f"Destination: {request.destination}\n"
            f"Trip length: {num_days} days ({request.start_date} to {request.end_date})\n"
            f"Budget: {request.budget} {request.currency}\n"
            f"Travel style: {request.travel_style}\n"
            f"Interests: {', '.join(request.interests) or 'general sightseeing'}"
        )

        # Memory Retrieval (SCIF pipeline stage 2) - failures here degrade
        # personalization, not correctness, so they're non-fatal to generation.
        try:
            memory_context = await self._memory.get_context(user_id, user_prompt)
            memory_text = memory_context.as_prompt_context()
            if memory_text:
                user_prompt += f"\n\n{memory_text}"
        except RuntimeError:
            pass  # e.g. GEMINI_API_KEY missing for embeddings - proceed without personalization

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

    async def set_saved(self, user_id: str, trip_id: str, is_saved: bool) -> None:
        await self._trips.set_saved(trip_id, is_saved)

        if not is_saved:
            return  # only "accept" signals feed memory for now, not un-saves

        trip = await self._trips.get_by_id(trip_id)
        if trip is None:
            return

        # Heuristic trip-level feature deltas (see module docstring) -
        # proxy for Phase 4's proper per-activity attribution.
        feature_deltas: dict[str, float] = {}
        if trip.budget > 0:
            spend_ratio = trip.estimated_total_cost / trip.budget
            feature_deltas["budget_sensitivity"] = -1.0 if spend_ratio < 0.85 else 1.0
        style_pace = {"relaxed": -1.0, "budget": -0.5, "balanced": 0.0, "adventure": 0.5, "luxury": 0.3}
        if trip.travel_style in style_pace:
            feature_deltas["pace_preference"] = style_pace[trip.travel_style]

        try:
            await self._memory.record_event(user_id, trip_id, "accept", feature_deltas)
            await self._memory.run_promotion(user_id)
        except RuntimeError:
            pass  # memory update failure shouldn't fail the save action itself

    async def delete_trip(self, trip_id: str) -> None:
        await self._trips.delete(trip_id)
