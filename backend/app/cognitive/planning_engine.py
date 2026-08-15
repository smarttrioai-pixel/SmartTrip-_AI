"""
Planning Engine for SmartTrip AI (SCIF Framework).

Orchestrates trip itinerary generation through the full SCIF pipeline:

    Stage 1   Retrieval Engine
              UserProfileEngine.get_preferences()
              MemoryEngine.get_context()

    Stage 2   Geocode destination (needed for weather)
              NavigationService.geocode() → lat/lon

    Stage 3   Live Context (NEW)
              LiveContextEngine.build_live_context()
              → Open-Meteo daily forecast per travel date
              SCIF pass 1: evaluate_activities() (weather only, pre-Qwen)
              → CognitiveDecision[]
              → derive_constraints() → human-readable weather rules

    Stage 4   Context Builder (ENHANCED)
              ContextBuilder.build_planning_prompt_with_context()
              → injects live context + SCIF decisions into Qwen prompt

    Stage 5   LLM Service → Provider → Model
              LLMService.generate_json() → Qwen 3.6 27B via Groq
              → raw itinerary JSON

    Stage 6   Itinerary Normalization
              normalize_days() — transport validation + chronological sort

    Stage 7   Place Enrichment (Geoapify)
              PlaceEnrichmentService.enrich_place() per activity
              → verifies real places; rejects fabricated names
              → returns opening_hours from Geoapify when available

    Stage 8   Opening-Hours Validation (NEW — post-Geoapify)
              LiveContextEngine.ingest_opening_hours()
              → parses Geoapify opening_hours per enriched place
              SCIF pass 2: evaluate_activities() (opening hours)
              → reject activities where Geoapify confirms place is closed
              → logs SCIF_DECISION per rejection

    Stage 9   Build CognitiveContext (for trace/logging)

    Stage 10  SCIF Cognitive Scoring + Explainability
              RecommendationEngine.score_and_rank()
              ExplainabilityEngine.explain()

    Stage 11  Risk Assessment
              RiskAssessmentEngine.score_trip()

Key design rule:
    Qwen GENERATES.  External providers VERIFY FACTS.  SCIF DECIDES.
    Qwen never determines: weather, opening hours, place existence,
    coordinates, ratings, images, or traffic conditions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta, date

from app.cognitive.context_engine import ContextEngine
from app.cognitive.explainability_engine import ExplainabilityEngine
from app.cognitive.live_context import CognitiveContext, CognitiveDecision, LiveContext
from app.cognitive.live_context_engine import LiveContextEngine
from app.cognitive.memory_engine import MemoryEngine
from app.cognitive.recommendation_engine import RecommendationEngine
from app.cognitive.risk_assessment_engine import RiskAssessmentEngine
from app.cognitive.user_profile_engine import UserProfileEngine
from app.integrations.navigation_service import NavigationService
from app.schemas.trip import GenerateItineraryRequest
from app.services.context_builder import ContextBuilder, ITINERARY_MAX_TOKENS
from app.services.itinerary_validator import normalize_days, _time_key
from app.services.llm_service import LLMService
from app.services.place_enrichment_service import PlaceEnrichmentService

logger = logging.getLogger(__name__)


@dataclass
class RawPlan:
    days: list[dict]
    estimated_total_cost: float
    risk_score: float
    cognitive_context: CognitiveContext | None = None
    scif_decisions: list[CognitiveDecision] = field(default_factory=list)


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
        place_enrichment_service: PlaceEnrichmentService,
        *,
        llm_service: LLMService,
        context_builder: ContextBuilder,
        live_context_engine: LiveContextEngine | None = None,
    ) -> None:
        self._profiles = user_profile_engine
        self._memory = memory_engine
        self._recommendations = recommendation_engine
        self._explainability = explainability_engine
        self._risk = risk_engine
        self._context = context_engine
        self._navigation = navigation_service
        self._place_enrichment = place_enrichment_service
        self._llm = llm_service
        self._context_builder = context_builder
        self._live_context_engine = live_context_engine

    async def generate_plan(self, user_id: str, request: GenerateItineraryRequest) -> RawPlan:
        num_days = (request.end_date - request.start_date).days + 1

        # ----------------------------------------------------------------
        # Stage 1: Retrieval Engine
        # ----------------------------------------------------------------
        preferences = await self._profiles.get_preferences(user_id)

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
            logger.warning("Memory context retrieval non-fatal error (proceeding without): %s", e)

        # ----------------------------------------------------------------
        # Stage 2: Geocode destination (needed for weather lookup)
        # ----------------------------------------------------------------
        destination_lat: float | None = None
        destination_lon: float | None = None
        try:
            geocode_result = await self._navigation.geocode(request.destination)
            if geocode_result:
                destination_lat = geocode_result["lat"]
                destination_lon = geocode_result["lon"]
        except Exception as e:
            logger.warning("Destination geocoding failed for '%s': %s", request.destination, e)

        # ----------------------------------------------------------------
        # Stage 3: Live Context + SCIF Pass 1 (pre-Qwen weather decisions)
        # ----------------------------------------------------------------
        live_context: LiveContext | None = None
        pre_decisions: list[CognitiveDecision] = []
        constraints: list[str] = []

        if self._live_context_engine is not None and destination_lat is not None:
            try:
                live_context = await self._live_context_engine.build_live_context(
                    destination=request.destination,
                    lat=destination_lat,
                    lon=destination_lon,
                    start_date=request.start_date,
                    end_date=request.end_date,
                )
                # Derive planning constraints for the Qwen prompt
                constraints = self._live_context_engine.derive_constraints(
                    live_context,
                    request.start_date,
                    request.end_date,
                )
                logger.info(
                    "SCIF_CONTEXT_BUILT destination=%s weather_sources=%s "
                    "constraints=%d",
                    request.destination,
                    live_context.available_sources,
                    len(constraints),
                )
            except Exception as exc:
                logger.warning(
                    "Live context build failed for '%s' (continuing without): %s",
                    request.destination, exc,
                )

        # Build CognitiveContext for prompt injection
        cognitive_ctx: CognitiveContext | None = None
        if live_context is not None:
            cognitive_ctx = CognitiveContext(
                current_request={
                    "destination": request.destination,
                    "start_date": request.start_date.isoformat(),
                    "end_date": request.end_date.isoformat(),
                    "budget": request.budget,
                    "currency": request.currency,
                    "transport": request.transport or "any",
                    "interests": request.interests,
                },
                memory_items=len(memory_context.relevant_preferences) if memory_context else 0,
                memory_summary=(
                    memory_context.as_prompt_context()[:200] if memory_context else ""
                ),
                live_context=live_context,
                constraints=constraints,
                decisions=[],  # populated after we have actual activities
            )

        # ----------------------------------------------------------------
        # Stage 4: Context Builder → Qwen prompt (with live context)
        # ----------------------------------------------------------------
        system_prompt, user_prompt = self._context_builder.build_planning_prompt_with_context(
            request=request,
            num_days=num_days,
            preferences=preferences,
            memory_context=memory_context,
            cognitive_context=cognitive_ctx,
        )

        # ----------------------------------------------------------------
        # Stage 5: LLM Service → Qwen 3.6 27B
        # ----------------------------------------------------------------
        ai_result = await self._llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=ITINERARY_MAX_TOKENS,
        )
        days = ai_result.get("days", [])
        if not isinstance(days, list):
            raise RuntimeError("LLM returned an invalid itinerary: days must be a list.")

        # ----------------------------------------------------------------
        # Stage 6: Itinerary Normalization
        # ----------------------------------------------------------------
        effective_transport = (
            request.transport
            if request.transport and request.transport != "any"
            else (preferences.transport or "any")
        )
        days = normalize_days(days, effective_transport)

        # ----------------------------------------------------------------
        # Stage 7: Place Enrichment (Geoapify)
        # ----------------------------------------------------------------
        used_place_ids: set[str] = set()

        for day in days:
            for activity in day.get("activities", []):
                category = str(activity.get("category") or "").lower()
                meal_type = activity.get("meal_type")
                food_query = activity.get("food_query")
                is_meal = category == "meal" or bool(meal_type or food_query)
                is_attraction = category in (
                    "attraction", "culture", "nature", "museum", "shopping", "sights"
                )

                if not (is_meal or is_attraction):
                    continue

                try:
                    enriched = await self._place_enrichment.enrich_place(
                        title=str(activity.get("title") or "Meal" if is_meal else activity.get("title") or ""),
                        location_hint=str(activity.get("location") or ""),
                        destination=request.destination,
                        category="meal" if is_meal else category,
                        meal_type=meal_type,
                        food_query=food_query,
                        used_place_ids=used_place_ids,
                    )
                except Exception as exc:
                    logger.warning(
                        "Place enrichment failed for %r in %r: %s",
                        activity.get("title"), request.destination, exc,
                    )
                    enriched = None

                if enriched and enriched.get("matched_place_name"):
                    if is_meal:
                        label = str(meal_type).title() if meal_type else ""
                        activity["title"] = (
                            f"{label} at {enriched['matched_place_name']}" if label
                            else enriched["matched_place_name"]
                        )
                    else:
                        activity["title"] = enriched["matched_place_name"]

                    activity["location"] = enriched.get("address") or enriched["matched_place_name"]
                    activity["place_enrichment"] = enriched

                    if enriched.get("source_id"):
                        used_place_ids.add(enriched["source_id"])

                elif is_attraction and enriched is None:
                    activity["place_enrichment"] = {"found": False, "source": "geoapify"}

        # ----------------------------------------------------------------
        # Stage 8: Opening-Hours Validation (post-Geoapify, SCIF Pass 2)
        # ----------------------------------------------------------------
        all_decisions: list[CognitiveDecision] = []

        if self._live_context_engine is not None and live_context is not None:
            try:
                # Ingest opening hours from enrichment results into live_context
                for day_idx, day in enumerate(days):
                    activity_date = request.start_date + timedelta(days=day_idx)
                    enriched_activities = [
                        act for act in day.get("activities", [])
                        if act.get("place_enrichment")
                    ]
                    for act in enriched_activities:
                        enrichment = act.get("place_enrichment") or {}
                        # Geoapify provides opening_hours in the enrichment dict
                        if enrichment.get("opening_hours") or enrichment.get("source_id"):
                            self._live_context_engine.ingest_opening_hours(
                                live=live_context,
                                enrichment_results=[act],
                                travel_date=activity_date,
                                activity_time_str=str(act.get("time") or "09:00"),
                            )

                # SCIF Pass 2: evaluate with opening hours now available
                all_decisions = self._live_context_engine.evaluate_activities(
                    days, live_context, request.start_date
                )

                # Apply reject decisions: flag rejected activities
                reject_map: dict[str, CognitiveDecision] = {
                    d.place: d for d in all_decisions if d.decision == "reject"
                }
                for day in days:
                    for activity in day.get("activities", []):
                        title = str(activity.get("title") or "")
                        if title in reject_map:
                            decision = reject_map[title]
                            activity["scif_rejected"] = True
                            activity["scif_rejection_reason"] = decision.reason
                            logger.info(
                                "PLACE_VALIDATION place=%r decision=reject reason=%r "
                                "evidence=%s",
                                title, decision.reason, decision.evidence,
                            )

            except Exception as exc:
                logger.warning(
                    "SCIF pass 2 (opening hours) failed for '%s' (continuing): %s",
                    request.destination, exc,
                )

        # ----------------------------------------------------------------
        # Stage 9: Build final CognitiveContext for trace
        # ----------------------------------------------------------------
        if cognitive_ctx is not None and live_context is not None:
            cognitive_ctx.decisions = all_decisions

        est_cost = ai_result.get("estimated_total_cost", request.budget)

        # ----------------------------------------------------------------
        # Stage 10: SCIF Cognitive Scoring + Explainability
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
            explained.sort(key=lambda a: _time_key(str(a.get("time", ""))))
            day["activities"] = explained

        # ----------------------------------------------------------------
        # Stage 11: Risk Assessment
        # ----------------------------------------------------------------
        risk_score = self._risk.score_trip(days, destination=request.destination)

        return RawPlan(
            days=days,
            estimated_total_cost=est_cost,
            risk_score=risk_score,
            cognitive_context=cognitive_ctx,
            scif_decisions=all_decisions,
        )
