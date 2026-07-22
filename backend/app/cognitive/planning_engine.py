"""
Planning Engine (SCIF Section 6, Phase 4 design Section 2.4).

Orchestrates the other 7 Cognitive Engines in a fixed sequence. This is
explicitly a linear pipeline, NOT yet a LangGraph agent graph - Phase 5
replaces this sequence with a Planner->{agents}->TourGuide graph. The
engines called here are designed so that swap doesn't require touching any
engine's internals, only how they're invoked.
"""
from __future__ import annotations

from app.cognitive.context_engine import ContextEngine
from app.cognitive.explainability_engine import ExplainabilityEngine
from app.cognitive.memory_engine import MemoryEngine
from app.cognitive.recommendation_engine import RecommendationEngine
from app.cognitive.risk_assessment_engine import RiskAssessmentEngine
from app.cognitive.user_profile_engine import UserProfileEngine
from app.core.gemini import generate_json
from app.schemas.trip import GenerateItineraryRequest

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


class RawPlan:
    def __init__(self, days: list[dict], estimated_total_cost: float, risk_score: float) -> None:
        self.days = days
        self.estimated_total_cost = estimated_total_cost
        self.risk_score = risk_score


class PlanningEngine:
    def __init__(
        self,
        user_profile_engine: UserProfileEngine,
        memory_engine: MemoryEngine,
        recommendation_engine: RecommendationEngine,
        explainability_engine: ExplainabilityEngine,
        risk_engine: RiskAssessmentEngine,
        context_engine: ContextEngine,
    ) -> None:
        self._profiles = user_profile_engine
        self._memory = memory_engine
        self._recommendations = recommendation_engine
        self._explainability = explainability_engine
        self._risk = risk_engine
        self._context = context_engine

    async def generate_plan(self, user_id: str, request: GenerateItineraryRequest) -> RawPlan:
        num_days = (request.end_date - request.start_date).days + 1
        base_prompt = (
            f"Destination: {request.destination}\n"
            f"Trip length: {num_days} days ({request.start_date} to {request.end_date})\n"
            f"Budget: {request.budget} {request.currency}\n"
            f"Travel style: {request.travel_style}\n"
            f"Interests: {', '.join(request.interests) or 'general sightseeing'}"
        )

        # 1. User Profile Engine
        preferences = await self._profiles.get_preferences(user_id)

        # 2. Memory Engine (built Phase 3, unchanged)
        user_prompt = base_prompt
        try:
            memory_context = await self._memory.get_context(user_id, base_prompt)
            memory_text = memory_context.as_prompt_context()
            if memory_text:
                user_prompt += f"\n\n{memory_text}"
        except RuntimeError:
            pass  # degrade personalization, not correctness

        # 3-4. Gemini generation (unchanged mechanism from Phase 3, richer prompt)
        ai_result = await generate_json(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt)
        days = ai_result["days"]

        # 5-7. Score, rank, and explain every activity
        daily_budget_hint = request.budget / max(num_days, 1)
        for day in days:
            scored_activities = self._recommendations.score_and_rank(
                day.get("activities", []), preferences, daily_budget_hint
            )
            # score_and_rank re-orders by score; re-attach explanations in
            # that order, then restore original time-of-day ordering for
            # display (ranking is for confidence, not itinerary sequence).
            explained = []
            for scored in scored_activities:
                explanation = self._explainability.explain(scored)
                activity = dict(scored.activity)
                activity["explanation"] = explanation.to_dict()
                explained.append(activity)
            explained.sort(key=lambda a: a.get("time", ""))
            day["activities"] = explained

        risk_score = self._risk.score_trip(days)

        return RawPlan(days=days, estimated_total_cost=ai_result["estimated_total_cost"], risk_score=risk_score)
