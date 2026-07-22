"""
Adaptive Learning Engine for SmartTrip AI (SCIF Framework).
Handles preference learning from user actions and triggers dynamic itinerary re-planning
upon real-time events (weather change, traffic disruption, skipped activity, place closed).
"""
from __future__ import annotations

import logging
from typing import Any

from app.cognitive.memory_engine import MemoryEngine
from app.models.trip import Trip

logger = logging.getLogger(__name__)

class AdaptiveLearningEngine:
    def __init__(self, memory_engine: MemoryEngine) -> None:
        self._memory = memory_engine

    async def on_trip_saved(self, user_id: str, trip: Trip) -> None:
        """Trigger behavioral updates when a user saves a trip."""
        feature_deltas: dict[str, float] = {}
        if trip.budget > 0:
            spend_ratio = trip.estimated_total_cost / trip.budget
            feature_deltas["budget_sensitivity"] = -1.0 if spend_ratio < 0.85 else 1.0

        style_pace = {"relaxed": -1.0, "budget": -0.5, "balanced": 0.0, "adventure": 0.5, "luxury": 0.3}
        if trip.travel_style in style_pace:
            feature_deltas["pace_preference"] = style_pace[trip.travel_style]

        try:
            await self._memory.record_event(user_id, trip.id, "accept", feature_deltas)
            await self._memory.run_promotion(user_id)
        except Exception as e:
            logger.warning("Memory update during trip save encountered non-fatal error: %s", e)

    async def evaluate_replanning_trigger(
        self, trip: Trip, event_type: str, event_details: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Evaluate if an external event (weather_change, place_closed, skipped_destination, traffic_delay)
        warrants regenerating part or all of the itinerary.
        """
        should_replan = event_type in [
            "weather_change",
            "traffic_disruption",
            "place_closed",
            "destination_skipped",
            "emergency_alert",
            "budget_changed",
        ]

        return {
            "should_replan": should_replan,
            "event_type": event_type,
            "impact_level": "high" if event_type in ["weather_change", "emergency_alert"] else "medium",
            "action": "Regenerate affected day activities with outdoor/indoor substitution" if should_replan else "Maintain current schedule",
            "event_details": event_details,
        }
