"""
Planning Engine for SmartTrip AI (SCIF Framework).

Orchestrates trip itinerary generation via the real Gemini call plus the
SCIF Cognitive Engines (Memory, Recommendation, Explainability, Risk).

Phase 5 (Retrieval Engine) changes:
  - generate_plan() now uses RetrievalEngine.retrieve_context() instead of
    the old MemoryEngine.get_context() when a RetrievalEngine is injected.
    This provides richer, multi-index context (Memory + Destination) rather
    than only user-preference embeddings.
  - Falls back to MemoryEngine.get_context() when no RetrievalEngine is
    injected (full backward compatibility).

This file previously tried app.agents.multi_agent_graph.MultiAgentGraph
("LangGraph 12-Agent System") as its PRIMARY path, falling back to this
same direct Gemini call only on exception. That graph's PlannerAgent
returned a hardcoded static itinerary and never raised, so the fallback
was unreachable — every generated itinerary was that same static template.
See the audit report (Section 4, finding #1) for full detail. The fake
graph call has been removed; the direct Gemini call is now unconditional.
Real multi-agent orchestration remains a separate, later decision per the
project's LangGraph implementation rules — not made here.
"""
from __future__ import annotations

import logging

from app.cognitive.context_engine import ContextEngine
from app.cognitive.explainability_engine import ExplainabilityEngine
from app.cognitive.memory_engine import MemoryEngine
from app.cognitive.recommendation_engine import RecommendationEngine
from app.cognitive.risk_assessment_engine import RiskAssessmentEngine
from app.cognitive.user_profile_engine import UserProfileEngine
from app.core.gemini import generate_json
from app.integrations.navigation_service import NavigationService
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
        navigation_service: NavigationService,
        retrieval_engine=None,  # app.engines.RetrievalEngine | None  (Phase 5)
    ) -> None:
        self._profiles = user_profile_engine
        self._memory = memory_engine
        self._recommendations = recommendation_engine
        self._explainability = explainability_engine
        self._risk = risk_engine
        self._context = context_engine
        self._navigation = navigation_service
        self._retrieval = retrieval_engine  # None → falls back to memory_engine.get_context()

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

        # --- Phase 5: use RetrievalEngine for richer context when available ---
        try:
            if self._retrieval is not None:
                # Multi-index: Memory (preferences + trip history) + Destination (places)
                structured_ctx = await self._retrieval.retrieve_context(
                    user_id,
                    base_prompt,
                    user_interests=preferences.interests,
                )
                context_text = structured_ctx.as_prompt_text()
                logger.debug(
                    "PlanningEngine: RetrievalEngine context | intent=%s | docs=%d | empty=%s",
                    structured_ctx.intent.value,
                    structured_ctx.total_documents_retrieved,
                    structured_ctx.is_empty(),
                )
            else:
                # Legacy path: MemoryEngine only
                memory_context = await self._memory.get_context(user_id, base_prompt)
                context_text = memory_context.as_prompt_context()

            if context_text:
                user_prompt += f"\n\n{context_text}"
        except Exception as e:
            logger.warning("Memory/retrieval context non-fatal error in planning: %s", e)

        ai_result = await generate_json(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt)
        days = ai_result.get("days", [])
        est_cost = ai_result.get("estimated_total_cost", request.budget)

        # Geocode the actual destination once per generation (not per
        # activity) so weather scoring reflects the real trip location.
        # If geocoding fails, destination_lat/lon stay None and
        # ContextEngine honestly marks weather as unavailable rather than
        # defaulting to any specific city's coordinates.
        destination_lat: float | None = None
        destination_lon: float | None = None
        try:
            geocode_result = await self._navigation.geocode(request.destination)
            if geocode_result:
                destination_lat = geocode_result["lat"]
                destination_lon = geocode_result["lon"]
        except Exception as e:
            logger.warning("Destination geocoding failed for '%s': %s", request.destination, e)

        # Score, rank, and attach SCIF explainability to every activity
        daily_budget_hint = request.budget / max(num_days, 1)
        for day in days:
            scored_activities = await self._recommendations.score_and_rank(
                day.get("activities", []),
                preferences,
                daily_budget_hint,
                destination_lat=destination_lat,
                destination_lon=destination_lon,
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
