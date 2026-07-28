"""
Business logic for the AI Trip Planner.

Phase 4: generation now goes through PlanningEngine (which internally
orchestrates the 7 Cognitive Engines) instead of calling Gemini directly.
Trip save now goes through AdaptiveLearningEngine instead of calling
MemoryEngine directly. This service's job is now purely persistence +
DTO shaping - all planning/scoring/explaining logic lives in app/cognitive/.
"""
from __future__ import annotations

from app.cognitive.adaptive_learning_engine import AdaptiveLearningEngine
from app.cognitive.planning_engine import PlanningEngine
from app.repositories.trip_repository import TripRepository
from app.schemas.trip import GenerateItineraryRequest, TripResponse


class TripPlannerService:
    def __init__(
        self,
        trip_repository: TripRepository,
        planning_engine: PlanningEngine,
        adaptive_learning_engine: AdaptiveLearningEngine,
    ) -> None:
        self._trips = trip_repository
        self._planning = planning_engine
        self._adaptive_learning = adaptive_learning_engine

    async def generate_itinerary(self, user_id: str, request: GenerateItineraryRequest) -> TripResponse:
        plan = await self._planning.generate_plan(user_id, request)

        trip = await self._trips.create(
            {
                "user_id": user_id,
                "destination": request.destination,
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "budget": request.budget,
                "currency": request.currency,
                "travel_style": request.travel_style,
                "days": plan.days,
                "estimated_total_cost": plan.estimated_total_cost,
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
            return

        trip = await self._trips.get_by_id(trip_id)
        if trip is None:
            return

        await self._adaptive_learning.on_trip_saved(user_id, trip)

    async def delete_trip(self, trip_id: str) -> None:
        await self._trips.delete(trip_id)
