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

Phase 4 changes:
- Consolidated to one real, async method (was already done in Phase 3).
- Added `personalization_score` factor — computed from the user's behavioral
  feature_weights (loaded from memory_behavioral/{uid}) against the
  activity's category and estimated cost. This is a real, computed value —
  not a placeholder.
- Updated composite formula: 0.30*budget + 0.30*interest + 0.25*context + 0.15*personalization
  (redistributed from 0.35/0.35/0.30 to accommodate personalization)
- distance_match and popularity_score still have no real data source —
  explicitly excluded and marked unavailable.
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
    personalization_score: float = 0.5
    unavailable_factors: list[str] = field(default_factory=list)


class RecommendationEngine:
    def __init__(self, context_engine: ContextEngine) -> None:
        self._context = context_engine

    async def score_and_rank(
        self,
        activities: list[dict],
        preferences: UserPreferences,
        daily_budget_hint: float,
        destination_lat: float | None = None,
        destination_lon: float | None = None,
        feature_weights: dict[str, float] | None = None,
    ) -> list[ScoredActivity]:
        """
        Real scoring pipeline:
        - budget_match: ratio of estimated_cost to daily_budget (real data)
        - interest_match: keyword overlap against declared interests (real data)
        - context: weather (real, Open-Meteo) + opening hours (real, Geoapify)
        - personalization_score: derived from behavioral feature_weights (real data
          from memory_behavioral Firestore doc, updated by user feedback)

        destination_lat/lon should come from a real geocode of the trip's
        destination — if unavailable, weather scoring is honestly marked
        unavailable rather than defaulting to any specific location's weather.

        feature_weights should come from MemoryContext.feature_weights, loaded
        from memory_behavioral/{uid}. If None/empty, personalization_score
        defaults to 0.5 (neutral — no personalization applied).
        """
        scored: list[ScoredActivity] = []
        weights = feature_weights or {}

        for activity in activities:
            context = await self._context.evaluate_context(
                activity, lat=destination_lat, lon=destination_lon
            )
            b_match = self._score_budget_fit(activity, daily_budget_hint)
            i_match = self._score_interest_match(activity, preferences.interests)
            p_score = self._score_personalization(activity, weights, daily_budget_hint)

            # Composite weights distributed across factors that are real.
            # distance_match and popularity_score have no real data source —
            # weight is not allocated to them.
            # personalization_score is now a real factor (behavioral memory).
            composite = round(
                0.30 * b_match
                + 0.30 * i_match
                + 0.25 * context.composite
                + 0.15 * p_score,
                2,
            )

            scored.append(
                ScoredActivity(
                    activity=activity,
                    budget_match=b_match,
                    interest_match=i_match,
                    context=context,
                    composite_score=composite,
                    personalization_score=p_score,
                    unavailable_factors=["distance_match", "popularity_score"] + context.unavailable_components,
                )
            )

        scored.sort(key=lambda s: s.composite_score, reverse=True)
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

    @staticmethod
    def _score_personalization(
        activity: dict,
        feature_weights: dict[str, float],
        daily_budget_hint: float,
    ) -> float:
        """
        Compute a personalization score from the user's behavioral feature_weights.

        This translates learned tendencies (stored in memory_behavioral/{uid} and
        updated by user feedback via POST /memory/feedback) into a numeric score
        that directly affects activity ranking.

        Scoring logic:
        - budget_sensitivity < 0 (user tends to reject expensive items):
          Penalize high-cost activities.
        - crowd_aversion > 0 (user avoids crowds):
          Activities with "crowd" in enrichment types get penalized.
        - novelty_seeking > 0 (user seeks novel experiences):
          Penalize familiar/generic activities; reward unique categories.
        - pace_preference: high = prefer more activities per day (no direct
          per-activity effect, omitted to avoid gaming).

        Returns 0.0–1.0. Default is 0.5 (neutral, no personalization).
        If feature_weights is empty, returns 0.5 (equivalent to no personalization).
        """
        if not feature_weights or all(abs(v) < 0.05 for v in feature_weights.values()):
            # No meaningful personalization data yet — neutral score
            return 0.5

        score = 0.5  # start neutral
        adjustments = 0

        # --- Budget sensitivity ---
        budget_weight = feature_weights.get("budget_sensitivity", 0.0)
        if abs(budget_weight) > 0.05 and daily_budget_hint > 0:
            cost = activity.get("estimated_cost", 0) or 0
            ratio = cost / daily_budget_hint if daily_budget_hint > 0 else 0
            if budget_weight < -0.1:  # user is budget-sensitive (rejects expensive things)
                # High-cost activities get penalized proportional to how budget-sensitive the user is
                cost_penalty = ratio * abs(budget_weight) * 0.3
                score -= cost_penalty
            elif budget_weight > 0.1:  # user is comfortable spending more
                # High-cost activities get a small bonus
                if ratio > 0.8:
                    score += abs(budget_weight) * 0.1
            adjustments += 1

        # --- Novelty seeking ---
        novelty_weight = feature_weights.get("novelty_seeking", 0.0)
        if abs(novelty_weight) > 0.05:
            category = str(activity.get("category") or "").lower()
            enrichment = activity.get("place_enrichment") or {}
            place_types = enrichment.get("place_types") or []
            # "novel" categories: nature, museum, culture (less common)
            novel_categories = {"nature", "museum", "culture"}
            generic_categories = {"meal", "transport", "shopping"}
            if novelty_weight > 0.1 and category in novel_categories:
                score += novelty_weight * 0.15
            elif novelty_weight < -0.1 and category in novel_categories:
                score -= abs(novelty_weight) * 0.1
            if novelty_weight > 0.1 and category in generic_categories:
                score -= novelty_weight * 0.05
            adjustments += 1

        # --- Crowd aversion ---
        crowd_weight = feature_weights.get("crowd_aversion", 0.0)
        if abs(crowd_weight) > 0.05:
            enrichment = activity.get("place_enrichment") or {}
            user_ratings_total = enrichment.get("user_ratings_total") or 0
            # Use number of reviews as a rough proxy for crowd/popularity
            if crowd_weight > 0.1 and user_ratings_total > 10000:
                # Very popular (crowded) place — user avoids crowds
                score -= crowd_weight * 0.15
            elif crowd_weight < -0.1 and user_ratings_total > 10000:
                # User doesn't mind crowds
                score += abs(crowd_weight) * 0.05
            adjustments += 1

        # Clamp to [0.0, 1.0]
        return round(max(0.0, min(1.0, score)), 3)
