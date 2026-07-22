"""
Recommendation Engine (SCIF Section 6, Phase 4 design Section 2.5).

Implements 3 of the eventual 12 pipeline stages this phase, against
Gemini's own candidate activities rather than an independent POI database
(that's Phase 6, via OpenTripMap). Distance/weather/crowd/safety/opening-
hours-as-hard-filter are deferred - see design doc Section 4 for the full
list of what this phase does not claim to do.

Interest matching uses keyword/substring overlap against declared
interests, NOT a Gemini embedding call per activity - see Phase 4 design
doc's approval-checkpoint resolution. This keeps itinerary generation to
exactly the calls it already made in Phase 3 (1 generation call, plus the
1 memory-context embedding call already built then) - no new per-activity
API cost.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.cognitive.context_engine import ContextEngine, ContextScoreBreakdown
from app.models.user import UserPreferences


@dataclass
class ScoredActivity:
    activity: dict
    budget_match: float
    interest_match: float
    context: ContextScoreBreakdown


class RecommendationEngine:
    def __init__(self, context_engine: ContextEngine) -> None:
        self._context = context_engine

    def score_and_rank(
        self,
        activities: list[dict],
        preferences: UserPreferences,
        daily_budget_hint: float,
    ) -> list[ScoredActivity]:
        scored = [
            ScoredActivity(
                activity=activity,
                budget_match=self._score_budget_fit(activity, daily_budget_hint),
                interest_match=self._score_interest_match(activity, preferences.interests),
                context=self._context.score_activity(activity),
            )
            for activity in activities
        ]
        scored.sort(key=lambda s: (s.budget_match + s.interest_match + s.context.composite), reverse=True)
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
