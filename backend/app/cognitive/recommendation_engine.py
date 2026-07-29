"""
Recommendation Engine for SmartTrip AI (SCIF Framework).

Previously this class had two competing scoring methods:
- `score_and_rank` (sync) - the one actually called by PlanningEngine, but
  every factor except budget_match and interest_match was a hardcoded
  fixed constant (weather_match=0.85, crowd_match=0.80, safety_match=0.90,
  popularity_score=0.85, distance_match=0.9 - always, regardless of the
  actual activity).
- `score_and_rank_async` - genuinely called ContextEngine for real
  weather/opening-hours scoring, but was never invoked anywhere (dead
  code), and still had its own hardcoded distance_match/popularity_score
  constants plus the Paris-default coordinate bug (now fixed separately in
  context_engine.py).

Consolidated to one real, async method. distance_match and
popularity_score have no real data source in this codebase yet (no
geocoded activity-to-activity distance calculation, no popularity data
API integrated) - rather than inventing plausible-looking constants for
them, they're explicitly marked unavailable and excluded from the
composite score's weighting, which is redistributed across the factors
that ARE real.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.cognitive.context_engine import ContextEngine, ContextScoreBreakdown
from app.models.user import UserPreferences


@dataclass
class ScoredActivity:
    activity: dict
    budget_match: float
    interest_match: float
    context: ContextScoreBreakdown
    composite_score: float
    unavailable_factors: list[str] = field(default_factory=list)


class RecommendationEngine:
    def __init__(
        self,
        context_engine: ContextEngine,
        retrieval_engine=None,  # app.engines.RetrievalEngine | None  (Phase 5)
    ) -> None:
        self._context = context_engine
        self._retrieval = retrieval_engine  # used to seed destination index

    async def score_and_rank(
        self,
        activities: list[dict],
        preferences: UserPreferences,
        daily_budget_hint: float,
        destination_lat: float | None = None,
        destination_lon: float | None = None,
    ) -> list[ScoredActivity]:
        """
        Real scoring pipeline: budget fit, interest match (keyword overlap
        against declared interests), and context (weather + opening-hours,
        via ContextEngine). destination_lat/lon should come from a real
        geocode of the trip's destination — if unavailable, weather scoring
        is honestly marked unavailable rather than defaulting to any
        specific location's weather.
        """
        scored: list[ScoredActivity] = []

        for activity in activities:
            context = await self._context.evaluate_context(
                activity, lat=destination_lat, lon=destination_lon
            )
            b_match = self._score_budget_fit(activity, daily_budget_hint)
            i_match = self._score_interest_match(activity, preferences.interests)

            # Composite weights redistributed across the factors that are
            # real (budget, interest, context) — no weight allocated to
            # distance/popularity since neither has a real data source yet.
            composite = round(0.35 * b_match + 0.35 * i_match + 0.30 * context.composite, 2)

            scored.append(
                ScoredActivity(
                    activity=activity,
                    budget_match=b_match,
                    interest_match=i_match,
                    context=context,
                    composite_score=composite,
                    unavailable_factors=["distance_match", "popularity_score"] + context.unavailable_components,
                )
            )

        scored.sort(key=lambda s: s.composite_score, reverse=True)

        # --- Phase 5: seed the DestinationVectorIndex with scored activities ---
        if self._retrieval is not None:
            import asyncio
            async def _index_activities() -> None:
                for s in scored:
                    try:
                        place_data = {
                            "name": s.activity.get("title", ""),
                            "description": s.activity.get("description", ""),
                            "location": s.activity.get("location", ""),
                            "category": "activity",
                            "rating": s.composite_score * 7,  # normalise to OTM 1-7 scale
                        }
                        await self._retrieval.index_place(place_data)
                    except Exception:
                        pass   # non-fatal: index seeding must never break scoring
            asyncio.ensure_future(_index_activities())

        return scored

    @staticmethod
    def _score_budget_fit(activity: dict, daily_budget_hint: float) -> float:
        if daily_budget_hint <= 0:
            return 0.5
        cost = activity.get("estimated_cost", 0) or 0
        ratio = cost / daily_budget_hint
        if ratio <= 0.5:
            return 1.0
        if ratio <= 1.0:
            return 0.8
        if ratio <= 1.5:
            return 0.4
        return 0.1

    @staticmethod
    def _score_interest_match(activity: dict, interests: list[str]) -> float:
        if not interests:
            return 0.5
        text = f"{activity.get('title', '')} {activity.get('description', '')}".lower()
        matches = sum(1 for interest in interests if interest.lower() in text)
        if matches == 0:
            return 0.3
        return min(1.0, 0.5 + 0.25 * matches)
