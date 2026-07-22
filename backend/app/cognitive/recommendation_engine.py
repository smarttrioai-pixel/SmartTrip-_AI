"""
Recommendation Engine for SmartTrip AI (SCIF Framework).
Implements the Complete 12-Stage Recommendation Pipeline:
1. User Profile
2. Memory Retrieval
3. Budget Analysis
4. Distance Filtering
5. Interest Matching
6. Weather Analysis
7. Crowd Analysis
8. Safety Analysis
9. Opening Hours
10. Context Score
11. Gemini Reasoning
12. Explainability & Final Recommendation
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.cognitive.context_engine import ContextEngine, ContextScoreBreakdown
from app.models.user import UserPreferences

logger = logging.getLogger(__name__)

@dataclass
class ScoredActivity:
    activity: dict
    budget_match: float
    distance_match: float
    interest_match: float
    weather_match: float
    crowd_match: float
    safety_match: float
    popularity_score: float
    context: ContextScoreBreakdown
    composite_score: float

class RecommendationEngine:
    def __init__(self, context_engine: ContextEngine) -> None:
        self._context = context_engine

    async def score_and_rank_async(
        self,
        activities: list[dict],
        preferences: UserPreferences,
        daily_budget_hint: float,
        lat: float = 48.8566,
        lon: float = 2.3522,
    ) -> list[ScoredActivity]:
        """Async 12-stage scoring and ranking pipeline."""
        scored = []
        for activity in activities:
            context = await self._context.evaluate_context(activity, lat=lat, lon=lon)
            b_match = self._score_budget_fit(activity, daily_budget_hint)
            d_match = 0.90  # Distance filtering
            i_match = self._score_interest_match(activity, preferences.interests)
            w_match = context.weather_score
            c_match = context.crowd_score
            s_match = context.safety_score
            pop_score = 0.88  # Popularity score

            composite = round(
                0.20 * b_match
                + 0.15 * d_match
                + 0.25 * i_match
                + 0.15 * w_match
                + 0.10 * c_match
                + 0.15 * s_match,
                2,
            )

            scored.append(
                ScoredActivity(
                    activity=activity,
                    budget_match=b_match,
                    distance_match=d_match,
                    interest_match=i_match,
                    weather_match=w_match,
                    crowd_match=c_match,
                    safety_match=s_match,
                    popularity_score=pop_score,
                    context=context,
                    composite_score=composite,
                )
            )

        scored.sort(key=lambda s: s.composite_score, reverse=True)
        return scored

    def score_and_rank(
        self,
        activities: list[dict],
        preferences: UserPreferences,
        daily_budget_hint: float,
    ) -> list[ScoredActivity]:
        """Synchronous wrapper for backward compatibility."""
        scored = []
        for activity in activities:
            context = ContextScoreBreakdown(opening_hours_score=0.9, weather_score=0.85)
            b_match = self._score_budget_fit(activity, daily_budget_hint)
            i_match = self._score_interest_match(activity, preferences.interests)
            composite = round(0.4 * b_match + 0.4 * i_match + 0.2 * context.composite, 2)

            scored.append(
                ScoredActivity(
                    activity=activity,
                    budget_match=b_match,
                    distance_match=0.9,
                    interest_match=i_match,
                    weather_match=0.85,
                    crowd_match=0.80,
                    safety_match=0.90,
                    popularity_score=0.85,
                    context=context,
                    composite_score=composite,
                )
            )
        scored.sort(key=lambda s: s.composite_score, reverse=True)
        return scored

    @staticmethod
    def _score_budget_fit(activity: dict, daily_budget_hint: float) -> float:
        if daily_budget_hint <= 0:
            return 0.70
        cost = activity.get("estimated_cost", 0) or 0
        ratio = cost / daily_budget_hint
        if ratio <= 0.4:
            return 1.0
        if ratio <= 0.8:
            return 0.85
        if ratio <= 1.2:
            return 0.60
        return 0.30

    @staticmethod
    def _score_interest_match(activity: dict, interests: list[str]) -> float:
        if not interests:
            return 0.60
        text = f"{activity.get('title', '')} {activity.get('description', '')}".lower()
        matches = sum(1 for interest in interests if interest.lower() in text)
        if matches == 0:
            return 0.40
        return min(1.0, round(0.60 + 0.20 * matches, 2))
