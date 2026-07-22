"""
Adaptive Learning Engine (SCIF Section 6, Phase 4 design Section 2.7).

This is a relocation of Phase 3's trip-save memory update logic (previously
inline in trip_service.py) behind a formal engine boundary, so
trip_service.py talks only to the Cognitive Layer, never to MemoryEngine
directly. The heuristic feature-delta computation itself is unchanged from
Phase 3 and is still a stopgap pending Phase 6's proper per-activity
attribution - flagged then, flagged again here, not quietly upgraded.
"""
from __future__ import annotations

from app.cognitive.memory_engine import MemoryEngine
from app.models.trip import Trip


class AdaptiveLearningEngine:
    def __init__(self, memory_engine: MemoryEngine) -> None:
        self._memory = memory_engine

    async def on_trip_saved(self, user_id: str, trip: Trip) -> None:
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
        except RuntimeError:
            pass  # memory update failure shouldn't fail the save action itself
