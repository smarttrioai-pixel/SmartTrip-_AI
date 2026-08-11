"""
  Planning Engine for SmartTrip AI (SCIF Framework).

  Orchestrates trip itinerary generation through the full SCIF pipeline:

      Planning Engine  (this file)
           ↓
      Retrieval Engine  (MemoryEngine.get_context — embeddings + preferences)
           ↓
      ContextBuilder    (assembles enriched system_prompt + user_prompt)
           ↓
      LLMService        (orchestration: retries, logging, circuit breaker)
           ↓
      GroqProvider      (Groq Inference API → qwen/qwen3-32b)

  No direct LLM calls are made in this file. The LLM call is delegated to
  LLMService.generate_json() which goes through the full provider abstraction
  stack. The SCIF Cognitive Engines (Memory, Recommendation, Explainability,
  Risk, Context, UserProfile) are all preserved and operate exactly as before.
  """
from __future__ import annotations

import logging

from app.cognitive.context_engine import ContextEngine
from app.cognitive.explainability_engine import ExplainabilityEngine
from app.cognitive.memory_engine import MemoryEngine
from app.cognitive.recommendation_engine import RecommendationEngine
from app.cognitive.risk_assessment_engine import RiskAssessmentEngine
from app.cognitive.user_profile_engine import UserProfileEngine
from app.integrations.navigation_service import NavigationService
from app.schemas.trip import GenerateItineraryRequest
from app.services.context_builder import ContextBuilder, ITINERARY_MAX_TOKENS
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


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
        *,
        llm_service: LLMService,
        context_builder: ContextBuilder,
    ) -> None:
        self._profiles = user_profile_engine
        self._memory = memory_engine
        self._recommendations = recommendation_engine
        self._explainability = explainability_engine
        self._risk = risk_engine
        self._context = context_engine
        self._navigation = navigation_service
        self._llm = llm_service
        self._context_builder = context_builder

    async def generate_plan(self, user_id: str, request: GenerateItineraryRequest) -> RawPlan:
        num_days = (request.end_date - request.start_date).days + 1

        # ----------------------------------------------------------------
        # Stage 1: Retrieval Engine
        # Fetch user preferences (UserProfileEngine) and memory context
        # (MemoryEngine — embedding-based retrieval of past preferences).
        # ----------------------------------------------------------------
        preferences = await self._profiles.get_preferences(user_id)

        # Build a base description for memory retrieval embedding
        base_query = (
            f"Trip to {request.destination} for {num_days} days, "
            f"budget {request.budget} {request.currency}, "
            f"style {request.travel_style}, "
            f"interests: {', '.join(request.interests) or 'general'}"
        )

        memory_context = None
        try:
            memory_context = await self._memory.get_context(user_id, base_query)
        except Exception as e:
            logger.warning(
                "Memory context retrieval non-fatal error (proceeding without): %s", e
            )

        # ----------------------------------------------------------------
        # Stage 2: Context Builder
        # Assemble the enriched (system_prompt, user_prompt) pair that
        # includes retrieved memory context and user preferences.
        # ----------------------------------------------------------------
        system_prompt, user_prompt = self._context_builder.build_planning_prompt(
            request=request,
            num_days=num_days,
            preferences=preferences,
            memory_context=memory_context,
        )

        # ----------------------------------------------------------------
        # Stage 3: LLM Service → Provider → Model
        # generate_json() handles validation, circuit breaker, and structured
        # logging. max_tokens=8000 provides headroom for multi-day itineraries.
        # ----------------------------------------------------------------
        ai_result = await self._llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=ITINERARY_MAX_TOKENS,
        )
        days = ai_result.get("days", [])
        est_cost = ai_result.get("estimated_total_cost", request.budget)

        # ----------------------------------------------------------------
        # Stage 4: Geocoding (for weather-based scoring in ContextEngine)
        # ----------------------------------------------------------------
        destination_lat: float | None = None
        destination_lon: float | None = None
        try:
            geocode_result = await self._navigation.geocode(request.destination)
            if geocode_result:
                destination_lat = geocode_result["lat"]
                destination_lon = geocode_result["lon"]
        except Exception as e:
            logger.warning(
                "Destination geocoding failed for '%s': %s", request.destination, e
            )

        # ----------------------------------------------------------------
        # Stage 5: SCIF Cognitive Scoring + Explainability
        # RecommendationEngine, ContextEngine, and ExplainabilityEngine
        # are all preserved and operate exactly as before.
        # ----------------------------------------------------------------
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

        # ----------------------------------------------------------------
        # Stage 6: Risk Assessment
        # ----------------------------------------------------------------
        risk_score = self._risk.score_trip(days, destination=request.destination)
        return RawPlan(days=days, estimated_total_cost=est_cost, risk_score=risk_score)
