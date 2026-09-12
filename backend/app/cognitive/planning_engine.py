"""
Planning Engine for SmartTrip AI (SCIF Framework).

Orchestrates trip itinerary generation through the full SCIF pipeline:

    Stage 1   SCIF Orchestrator (replaces ad-hoc Stages 1–3)
              Runs 5 specialized planning agents in sequence:
                NavigationAgent  → Geoapify: destination lat/lon
                MemoryAgent      → Firestore: persistent user preferences
                WeatherAgent     → Open-Meteo: weather forecast + constraints
                BudgetAgent      → Internal: budget breakdown + constraints
                SafetyAgent      → Internal heuristic: safety constraints
              Produces CognitivePlanningContext (canonical SCIF input)
              SCIF PASS 1: derive all planning constraints from agent outputs

    Stage 2   Context Builder (ENHANCED)
              ContextBuilder.build_planning_prompt_full()
              → injects CognitivePlanningContext into Qwen prompt
              → weather + budget + profile + memory + SCIF constraints

    Stage 3   LLM Service → Provider → Model
              LLMService.generate_json() → Qwen 3.6 27B via Groq
              → raw itinerary JSON (planning INTENT only, no real places)

    Stage 4   Itinerary Normalization
              normalize_days() — transport validation + chronological sort

    Stage 5   Qwen intent → Activity schema normalization
              _normalize_pre_enrichment() — map slot_intent/reason/place_query

    Stage 6   Place Enrichment (Google Primary → Geoapify Fallback)
              PlaceEnrichmentService.enrich_place() per activity
              → verifies real places; rejects fabricated names
              → returns opening_hours from Geoapify when available

    Stage 6b  Post-enrichment Activity schema validation sweep

    Stage 7   Opening-Hours Validation (SCIF Pass 2 — post-enrichment)
              LiveContextEngine.ingest_opening_hours()
              SCIF Pass 2: evaluate_activities()
              → reject activities where Geoapify confirms place is closed
              → logs SCIF_DECISION per rejection

    Stage 8   Build CognitiveContext for trace
              Attaches CognitivePlanningContext for full pipeline trace

    Stage 9   SCIF Cognitive Scoring + Explainability
              RecommendationEngine.score_and_rank()
              ExplainabilityEngine.explain()

    Stage 10  Risk Assessment (SafetyAgent post-scoring)
              RiskAssessmentEngine.score_trip()

Key design rule:
    Qwen GENERATES.  External providers VERIFY FACTS.  SCIF DECIDES.
    Qwen never determines: weather, opening hours, place existence,
    coordinates, ratings, images, or traffic conditions.

SCIF Pipeline:
    Memory + Profile + Retrieval + Cognitive Context + Agent Outputs
        ↓
    SCIF Pass 1 (SCIFOrchestrator)
        ↓
    Qwen Cognitive Reasoning
        ↓
    Google Places Grounding (PlaceEnrichmentService)
        ↓
    SCIF Pass 2 (LiveContextEngine.evaluate_activities)
        ↓
    Explainability + Risk
        ↓
    Final Itinerary
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta, date

from app.agents.budget_agent import BudgetAgent
from app.agents.memory_agent import MemoryAgent
from app.agents.navigation_agent import NavigationAgent
from app.agents.safety_agent import SafetyAgent
from app.agents.scif_orchestrator import SCIFOrchestrator
from app.agents.weather_agent import WeatherAgent
from app.cognitive.context_engine import ContextEngine
from app.cognitive.explainability_engine import ExplainabilityEngine
from app.cognitive.live_context import (
    CognitiveContext,
    CognitiveDecision,
    CognitivePlanningContext,
    LiveContext,
    PipelineStage,
)
from app.cognitive.live_context_engine import LiveContextEngine
from app.cognitive.memory_engine import MemoryEngine
from app.cognitive.place_consistency import PlaceConsistencyValidator, get_place_consistency_validator
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


def _normalize_pre_enrichment(activity: dict, destination: str) -> None:
    """
    Map Qwen's new intent-schema fields onto the required Activity schema
    fields (title, description, location).

    Qwen's new schema outputs:
        slot_intent    → maps to  title      (if title missing)
        reason         → maps to  description (if description missing)
        place_query    → maps to  location    (if location missing)

    Qwen's old schema outputs title/description/location directly.
    Both schemas are supported simultaneously.

    This function is called on every activity BEFORE enrichment so that:
    - Non-enriched activities (transport, other) always have all fields.
    - Enriched activities have valid fallbacks before overwriting.
    - The Activity Pydantic model never sees a missing required field.

    Rules:
    - title:       slot_intent → title → place_query → category fallback
    - description: reason → slot_intent summary → category fallback
    - location:    existing location → destination (never empty)
    """
    # ---- title ----
    if not activity.get("title"):
        title_candidate = (
            str(activity.get("slot_intent") or "")
            or str(activity.get("place_query") or "")
            or str(activity.get("category") or "Activity").replace("_", " ").title()
        )
        activity["title"] = title_candidate.strip() or "Activity"
        logger.debug(
            "activity_normalize title_from_intent title=%r slot_intent=%r",
            activity["title"], activity.get("slot_intent"),
        )

    # ---- description ----
    if not activity.get("description"):
        description_candidate = (
            str(activity.get("reason") or "")
            or str(activity.get("slot_intent") or "")
            or str(activity.get("title") or "")
        )
        activity["description"] = description_candidate.strip() or "Part of your itinerary."
        logger.debug(
            "activity_normalize description_from_reason description=%r reason=%r",
            activity["description"][:60], activity.get("reason"),
        )

    # ---- location ----
    if not activity.get("location"):
        location_candidate = (
            str(activity.get("place_query") or "")
            or destination
        )
        activity["location"] = location_candidate.strip() or destination
        logger.debug(
            "activity_normalize location_from_destination location=%r",
            activity["location"],
        )


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
        place_consistency_validator: PlaceConsistencyValidator | None = None,
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
        self._consistency_validator = (
            place_consistency_validator or get_place_consistency_validator()
        )

        # Build SCIFOrchestrator from the existing engines
        self._scif_orchestrator = SCIFOrchestrator(
            memory_agent=MemoryAgent(memory_engine),
            weather_agent=WeatherAgent(live_context_engine) if live_context_engine else WeatherAgent(_NoopLiveContextEngine()),
            navigation_agent=NavigationAgent(navigation_service),
            budget_agent=BudgetAgent(),
            safety_agent=SafetyAgent(risk_engine),
            user_profile_engine=user_profile_engine,
        )

    async def generate_plan(self, user_id: str, request: GenerateItineraryRequest) -> RawPlan:
        num_days = (request.end_date - request.start_date).days + 1

        # ----------------------------------------------------------------
        # Stage 1: SCIF Orchestrator
        # Replaces old ad-hoc Stages 1 (profile/memory) + 2 (geocode) + 3 (weather)
        # Runs all 5 agents and produces CognitivePlanningContext.
        # SCIF Pass 1 runs inside the orchestrator.
        # ----------------------------------------------------------------
        t_stage1 = time.monotonic()
        planning_ctx, preferences, memory_context = await self._scif_orchestrator.run(
            user_id=user_id,
            destination=request.destination,
            start_date=request.start_date,
            end_date=request.end_date,
            budget=request.budget,
            currency=request.currency,
            travel_style=request.travel_style,
            transport=request.transport or "any",
            interests=list(request.interests or []),
        )
        destination_lat = planning_ctx.lat
        destination_lon = planning_ctx.lon
        live_context = planning_ctx.live_context

        logger.info(
            "SCIF_STAGE1_COMPLETE destination=%r agents=%d constraints=%d latency_ms=%.0f",
            request.destination,
            len(planning_ctx.agent_outputs),
            len(planning_ctx.all_constraints()),
            (time.monotonic() - t_stage1) * 1000,
        )

        # ----------------------------------------------------------------
        # Stage 2: Context Builder → Qwen prompt (SCIF-enhanced)
        # Uses build_planning_prompt_full() with CognitivePlanningContext
        # ----------------------------------------------------------------
        system_prompt, user_prompt = self._context_builder.build_planning_prompt_full(
            planning_context=planning_ctx,
            request=request,
            num_days=num_days,
            preferences=preferences,
            memory_context=memory_context,
        )

        planning_ctx.add_stage(PipelineStage(
            stage_name="PROMPT_ASSEMBLY",
            component="ContextBuilder",
            status="ok",
            summary=(
                f"Qwen prompt assembled with "
                f"{len(planning_ctx.all_constraints())} SCIF constraints, "
                f"memory={'yes' if planning_ctx.memory_items > 0 else 'no'}, "
                f"weather={'yes' if live_context.weather_by_date else 'no'}, "
                f"budget={'yes' if planning_ctx.budget_context else 'no'}."
            ),
            data_source="internal",
        ))

        # ----------------------------------------------------------------
        # Stage 3: LLM Service → Qwen 3.6 27B
        # ----------------------------------------------------------------
        t_llm = time.monotonic()
        ai_result = await self._llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=ITINERARY_MAX_TOKENS,
        )
        days = ai_result.get("days", [])
        if not isinstance(days, list):
            raise RuntimeError("LLM returned an invalid itinerary: days must be a list.")

        llm_latency_ms = (time.monotonic() - t_llm) * 1000
        total_activities = sum(len(d.get("activities", [])) for d in days)
        planning_ctx.add_stage(PipelineStage(
            stage_name="LLM_GENERATION",
            component="LLMService/Qwen3.6-27B",
            status="ok",
            summary=(
                f"Qwen generated candidate itinerary: "
                f"{len(days)} days, {total_activities} activities."
            ),
            latency_ms=llm_latency_ms,
            items=total_activities,
            data_source="Groq/Qwen3.6-27B",
        ))

        # ----------------------------------------------------------------
        # Stage 4: Itinerary Normalization
        # ----------------------------------------------------------------
        effective_transport = (
            request.transport
            if request.transport and request.transport != "any"
            else (preferences.transport or "any")
        )
        days = normalize_days(days, effective_transport)

        # ----------------------------------------------------------------
        # Stage 5: Qwen intent → Activity schema normalization
        # Map new Qwen intent fields (slot_intent, reason, place_query)
        # onto the required Activity schema fields (title, description,
        # location) so that every activity has valid values BEFORE Stage 6
        # enrichment tries to overwrite them.
        # ----------------------------------------------------------------
        for day in days:
            for activity in day.get("activities", []):
                _normalize_pre_enrichment(activity, request.destination)

        # ----------------------------------------------------------------
        # Stage 6: Place Enrichment (Google Primary → Geoapify Fallback)
        # ----------------------------------------------------------------
        t_enrich = time.monotonic()
        used_place_ids: set[str] = set()

        # Stats for cognitive trace
        _provider_stats: dict[str, int] = {
            "google": 0, "geoapify": 0, "none": 0,
            "attractions_found": 0, "restaurants_found": 0,
            "verified": 0, "rejected": 0,
        }
        _rejection_reasons: list[dict] = []

        # User preferences from memory (for TouristRanker)
        user_prefs: list[str] = []
        if memory_context and memory_context.relevant_preferences:
            user_prefs = [
                p.value if hasattr(p, "value") else str(p)
                for p in memory_context.relevant_preferences[:10]
            ]
        user_prefs += list(preferences.interests or [])

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

                # Read new Qwen intent fields (with fallback to old title field)
                slot_intent = (
                    str(activity.get("slot_intent") or "")
                    or str(activity.get("title") or "")
                )
                place_query = (
                    str(activity.get("place_query") or "")
                    or food_query
                    or slot_intent
                )
                place_type_hint = activity.get("place_type_hint")

                # Use slot_intent as the display title until enrichment provides a real name
                if not activity.get("title") and slot_intent:
                    activity["title"] = slot_intent

                try:
                    enriched = await self._place_enrichment.enrich_place(
                        title=slot_intent,
                        location_hint=str(activity.get("location") or ""),
                        destination=request.destination,
                        slot_intent=slot_intent,
                        place_query=place_query,
                        place_type_hint=place_type_hint,
                        category="meal" if is_meal else category,
                        meal_type=meal_type,
                        food_query=food_query,
                        used_place_ids=used_place_ids,
                        user_preferences=user_prefs,
                    )
                except Exception as exc:
                    logger.warning(
                        "Place enrichment failed for %r in %r: %s",
                        slot_intent, request.destination, exc,
                    )
                    enriched = None

                if enriched and enriched.get("matched_place_name"):
                    # --- Set title from verified Google/Geoapify place name ---
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

                    # description: keep Qwen reason if exists, else build from enrichment
                    if not activity.get("description") or activity.get("description") == activity.get("slot_intent"):
                        category_label = (
                            enriched.get("category") or ""
                        ).replace("_", " ").title()
                        activity["description"] = (
                            activity.get("reason")
                            or f"{category_label} in {request.destination}.".strip()
                            or f"Visit {enriched['matched_place_name']} in {request.destination}."
                        )

                    # --- Place/Activity Consistency Validation ---
                    place_types = enriched.get("place_types") or []
                    if place_types and not is_meal:
                        self._consistency_validator.validate_and_fix(
                            activity,
                            place_name=enriched["matched_place_name"],
                            place_types=place_types,
                            destination=request.destination,
                            rating=enriched.get("rating"),
                            address=enriched.get("address"),
                        )

                    # Update dedup set
                    source_id = enriched.get("source_id") or enriched.get("place_id")
                    if source_id:
                        used_place_ids.add(source_id)

                    # Stats
                    provider = enriched.get("provider_used", enriched.get("source", "unknown"))
                    if "google" in provider:
                        _provider_stats["google"] += 1
                    elif "geoapify" in provider:
                        _provider_stats["geoapify"] += 1
                    if is_meal:
                        _provider_stats["restaurants_found"] += 1
                    else:
                        _provider_stats["attractions_found"] += 1
                    _provider_stats["verified"] += 1

                elif is_attraction and enriched is None:
                    activity["place_enrichment"] = {
                        "found": False,
                        "source": "google",
                        "reason": "no_tourist_relevant_candidate",
                    }
                    _provider_stats["rejected"] += 1
                    _rejection_reasons.append({
                        "slot_intent": slot_intent,
                        "decision": "reject",
                        "reason": "PLACE_NOT_VERIFIED_no_tourist_candidate",
                    })

        enrich_latency_ms = (time.monotonic() - t_enrich) * 1000
        planning_ctx.add_stage(PipelineStage(
            stage_name="PLACE_VERIFICATION",
            component="PlaceEnrichmentService",
            status="ok",
            summary=(
                f"Place enrichment complete: "
                f"{_provider_stats['verified']} verified "
                f"({_provider_stats['google']} Google, {_provider_stats['geoapify']} Geoapify), "
                f"{_provider_stats['rejected']} rejected. "
                f"Restaurants: {_provider_stats['restaurants_found']}."
            ),
            latency_ms=enrich_latency_ms,
            items=_provider_stats["verified"],
            data_source="Google Places / Geoapify",
        ))

        # ----------------------------------------------------------------
        # Stage 6b: Post-enrichment Activity schema validation sweep
        # Guarantee every activity still has title, description, location.
        # ----------------------------------------------------------------
        missing_fields_count = 0
        for day in days:
            for activity in day.get("activities", []):
                if not activity.get("title") or not activity.get("description") or not activity.get("location"):
                    _normalize_pre_enrichment(activity, request.destination)
                    missing_fields_count += 1

        if missing_fields_count:
            logger.warning(
                "ACTIVITY_SCHEMA_SWEEP destination=%r fixed_activities=%d "
                "(enrichment left required fields empty)",
                request.destination, missing_fields_count,
            )

        # ----------------------------------------------------------------
        # Stage 7: Opening-Hours Validation (SCIF Pass 2 — post-enrichment)
        # ----------------------------------------------------------------
        all_decisions: list[CognitiveDecision] = []

        if self._live_context_engine is not None and live_context is not None:
            t_scif2 = time.monotonic()
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

                scif2_latency_ms = (time.monotonic() - t_scif2) * 1000
                approve_count = sum(1 for d in all_decisions if d.decision == "approve")
                reject_count = sum(1 for d in all_decisions if d.decision == "reject")
                reschedule_count = sum(1 for d in all_decisions if d.decision == "reschedule")
                planning_ctx.add_stage(PipelineStage(
                    stage_name="SCIF_PASS_2",
                    component="LiveContextEngine",
                    status="ok",
                    summary=(
                        f"SCIF Pass 2: {len(all_decisions)} decisions — "
                        f"{approve_count} approve, {reject_count} reject, "
                        f"{reschedule_count} reschedule."
                    ),
                    latency_ms=scif2_latency_ms,
                    items=len(all_decisions),
                    data_source="Geoapify/opening-hours + Open-Meteo/weather",
                ))

            except Exception as exc:
                logger.warning(
                    "SCIF pass 2 (opening hours) failed for '%s' (continuing): %s",
                    request.destination, exc,
                )
                planning_ctx.add_stage(PipelineStage(
                    stage_name="SCIF_PASS_2",
                    component="LiveContextEngine",
                    status="error",
                    summary=f"SCIF Pass 2 failed: {exc}",
                    data_source="Geoapify/opening-hours",
                ))

        # ----------------------------------------------------------------
        # Stage 8: Build CognitiveContext for trace
        # Bridges old CognitiveContext trace format with new planning_ctx
        # ----------------------------------------------------------------
        _google_trace = {
            "place_provider": (
                "google" if _provider_stats["google"] > 0
                else ("geoapify" if _provider_stats["geoapify"] > 0 else "none")
            ),
            "candidate_stats": {
                "attractions_found": _provider_stats["attractions_found"],
                "restaurants_found": _provider_stats["restaurants_found"],
                "verified": _provider_stats["verified"],
                "rejected": _provider_stats["rejected"],
                "google_results": _provider_stats["google"],
                "geoapify_results": _provider_stats["geoapify"],
            },
            "rejected_slots": _rejection_reasons[:10],
        }

        # Build the backward-compatible CognitiveContext that wraps planning_ctx
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
            memory_items=planning_ctx.memory_items,
            memory_summary=planning_ctx.memory_summary,
            live_context=live_context if live_context is not None else LiveContext(),
            constraints=planning_ctx.all_constraints(),
            decisions=all_decisions,
            provider_trace=_google_trace,
            planning_context=planning_ctx,  # attach full SCIF pipeline context
        )

        est_cost = ai_result.get("estimated_total_cost", request.budget)

        # ----------------------------------------------------------------
        # Stage 9: SCIF Cognitive Scoring + Explainability
        # Feature weights from behavioral memory (memory_behavioral/{uid})
        # are now passed to score_and_rank() so they numerically affect
        # the personalization_score component of composite_score.
        # ----------------------------------------------------------------
        t_score = time.monotonic()
        daily_budget_hint = request.budget / max(num_days, 1)
        # Extract behavioral feature_weights from memory context
        # (loaded by MemoryAgent from Firestore in Stage 1)
        behavioral_weights: dict[str, float] = {}
        if memory_context is not None:
            behavioral_weights = memory_context.feature_weights or {}

        personalization_active = any(abs(v) > 0.05 for v in behavioral_weights.values())

        for day in days:
            scored_activities = await self._recommendations.score_and_rank(
                day.get("activities", []),
                preferences,
                daily_budget_hint,
                destination_lat=destination_lat,
                destination_lon=destination_lon,
                feature_weights=behavioral_weights,
            )
            explained = []
            for scored in scored_activities:
                explanation = self._explainability.explain(scored)
                activity = dict(scored.activity)
                activity["explanation"] = explanation.to_dict()
                explained.append(activity)
            explained.sort(key=lambda a: _time_key(str(a.get("time", ""))))
            day["activities"] = explained


        planning_ctx.add_stage(PipelineStage(
            stage_name="RECOMMENDATION_EXPLAINABILITY",
            component="RecommendationEngine + ExplainabilityEngine",
            status="ok",
            summary="Activities scored by budget fit, interest match, and weather context. Explanations generated.",
            latency_ms=(time.monotonic() - t_score) * 1000,
            data_source="internal",
        ))

        # ----------------------------------------------------------------
        # Stage 10: Risk Assessment
        # ----------------------------------------------------------------
        risk_score = self._risk.score_trip(days, destination=request.destination)
        planning_ctx.add_stage(PipelineStage(
            stage_name="RISK_ASSESSMENT",
            component="RiskAssessmentEngine",
            status="ok",
            summary=(
                f"Trip risk score: {risk_score:.2f} (0.0=safe, 1.0=high risk). "
                f"Source: internal keyword-based heuristic."
            ),
            data_source="internal_heuristic",
        ))

        logger.info(
            "TRIP_GENERATION_COMPLETE destination=%r days=%d activities=%d "
            "risk=%.2f stages=%d",
            request.destination, len(days),
            sum(len(d.get("activities", [])) for d in days),
            risk_score, len(planning_ctx.pipeline_stages),
        )

        return RawPlan(
            days=days,
            estimated_total_cost=est_cost,
            risk_score=risk_score,
            cognitive_context=cognitive_ctx,
            scif_decisions=all_decisions,
        )


class _NoopLiveContextEngine:
    """
    Fallback for when no LiveContextEngine is configured.
    WeatherAgent will receive this and return unavailable status.
    """
    async def build_live_context(self, **kwargs):
        return LiveContext()

    def derive_constraints(self, live, start, end):
        return []

    def ingest_opening_hours(self, **kwargs):
        pass

    def evaluate_activities(self, days, live, start):
        return []
