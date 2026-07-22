"""
Planning Engine for SmartTrip AI (SCIF Framework).
Orchestrates trip itinerary generation using the LangGraph 12-Agent System
with fallback to linear SCIF Cognitive Engine scoring.
"""
from __future__ import annotations

import logging
from app.agents.multi_agent_graph import get_multi_agent_graph
from app.cognitive.context_engine import ContextEngine
from app.cognitive.explainability_engine import ExplainabilityEngine
from app.cognitive.memory_engine import MemoryEngine
from app.cognitive.recommendation_engine import RecommendationEngine
from app.cognitive.risk_assessment_engine import RiskAssessmentEngine
from app.cognitive.user_profile_engine import UserProfileEngine
from app.core.gemini import generate_json
from app.schemas.trip import GenerateItineraryRequest

logger = logging.getLogger(__name__)

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
}"""

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
        self._graph = get_multi_agent_graph()

    async def generate_plan(self, user_id: str, request: GenerateItineraryRequest) -> RawPlan:
        num_days = (request.end_date - request.start_date).days + 1
        base_prompt = (
            f"Destination: {request.destination}\n"
            f"Trip length: {num_days} days ({request.start_date} to {request.end_date})\n"
            f"Budget: {request.budget} {request.currency}\n"
            f"Travel style: {request.travel_style}\n"
            f"Interests: {', '.join(request.interests) or 'general sightseeing'}"
        )

        preferences = await self._profiles.get_preferences(user_id)
        user_prompt = base_prompt

        try:
            memory_context = await self._memory.get_context(user_id, base_prompt)
            memory_text = memory_context.as_prompt_context()
            if memory_text:
                user_prompt += f"\n\n{memory_text}"
        except Exception as e:
            logger.warning("Memory context retrieval non-fatal error: %s", e)

        # 1. Try LangGraph Multi-Agent execution
        try:
            agent_state = await self._graph.execute_graph({
                "user_id": user_id,
                "destination": request.destination,
                "start_date": str(request.start_date),
                "end_date": str(request.end_date),
                "budget": request.budget,
                "currency": request.currency,
                "travel_style": request.travel_style,
                "interests": request.interests,
                "current_request": base_prompt,
            })
            raw_plan_dict = agent_state.get("raw_plan", {})
            days = raw_plan_dict.get("days", [])
            est_cost = raw_plan_dict.get("estimated_total_cost", request.budget * 0.9)
        except Exception as e:
            logger.warning("Multi-agent graph fallback to direct Gemini generation: %s", e)
            ai_result = await generate_json(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt)
            days = ai_result.get("days", [])
            est_cost = ai_result.get("estimated_total_cost", request.budget)

        # 2. Score, rank, and attach SCIF explainability to every activity
        daily_budget_hint = request.budget / max(num_days, 1)
        for day in days:
            scored_activities = self._recommendations.score_and_rank(
                day.get("activities", []), preferences, daily_budget_hint
            )
            explained = []
            for scored in scored_activities:
                explanation = self._explainability.explain(scored)
                activity = dict(scored.activity)
                activity["explanation"] = explanation.to_dict()
                explained.append(activity)
            explained.sort(key=lambda a: a.get("time", ""))
            day["activities"] = explained

        risk_score = self._risk.score_trip(days, destination=request.destination)
        return RawPlan(days=days, estimated_total_cost=est_cost, risk_score=risk_score)
