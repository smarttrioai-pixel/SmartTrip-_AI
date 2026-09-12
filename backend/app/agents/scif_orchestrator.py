"""
SCIF Orchestrator for SmartTrip AI.

The SCIFOrchestrator coordinates all specialized planning agents and
assembles the canonical CognitivePlanningContext before Qwen generates.

SCIF Pipeline (Pre-Qwen):
    NavigationAgent  → destination coordinates
    MemoryAgent      → persistent user preferences (Firestore)
    WeatherAgent     → real weather forecast (Open-Meteo)
    BudgetAgent      → budget breakdown and constraints (internal)
    SafetyAgent      → safety heuristics and constraints (internal)
                     ↓
              SCIF PASS 1
                     ↓
       CognitivePlanningContext (all inputs merged)
                     ↓
             ContextBuilder → Qwen prompt

Key design principles:
- Each agent runs independently. One agent's failure does NOT abort generation.
- All agent outputs are recorded in the trace for research audit.
- No agent fabricates data. Unavailability is honestly reported.
- The CognitivePlanningContext is the single source of truth for Qwen.
- No LangGraph: direct async orchestration is sufficient and more honest.
"""
from __future__ import annotations

import logging
import time
from datetime import date

from app.agents.budget_agent import BudgetAgent
from app.agents.memory_agent import MemoryAgent
from app.agents.navigation_agent import NavigationAgent
from app.agents.safety_agent import SafetyAgent
from app.agents.weather_agent import WeatherAgent
from app.cognitive.live_context import (
    AgentOutput,
    CognitivePlanningContext,
    PipelineStage,
)
from app.cognitive.memory_engine import MemoryContext, MemoryEngine
from app.cognitive.user_profile_engine import UserProfileEngine
from app.models.user import UserPreferences

logger = logging.getLogger(__name__)


class SCIFOrchestrator:
    """
    Orchestrates all specialized planning agents and produces the canonical
    CognitivePlanningContext that is consumed by ContextBuilder → Qwen.

    This replaces the ad-hoc Stage 3 / Stage 4 logic in PlanningEngine with
    a named, auditable, per-agent pipeline.
    """

    def __init__(
        self,
        memory_agent: MemoryAgent,
        weather_agent: WeatherAgent,
        navigation_agent: NavigationAgent,
        budget_agent: BudgetAgent,
        safety_agent: SafetyAgent,
        user_profile_engine: UserProfileEngine,
    ) -> None:
        self._memory = memory_agent
        self._weather = weather_agent
        self._navigation = navigation_agent
        self._budget = budget_agent
        self._safety = safety_agent
        self._profiles = user_profile_engine

    async def run(
        self,
        user_id: str,
        destination: str,
        start_date: date,
        end_date: date,
        budget: float,
        currency: str,
        travel_style: str,
        transport: str,
        interests: list[str],
    ) -> tuple[CognitivePlanningContext, UserPreferences, MemoryContext | None]:
        """
        Run all pre-Qwen agents and produce CognitivePlanningContext.

        Returns:
            (CognitivePlanningContext, UserPreferences, MemoryContext | None)

        The CognitivePlanningContext is the complete SCIF input for Qwen.
        UserPreferences and MemoryContext are also returned so PlanningEngine
        can pass them to ContextBuilder (backward-compatible).
        """
        t_total = time.monotonic()
        num_days = (end_date - start_date).days + 1

        ctx = CognitivePlanningContext(
            destination=destination,
            start_date_iso=start_date.isoformat(),
            end_date_iso=end_date.isoformat(),
            num_days=num_days,
            budget=budget,
            currency=currency,
            travel_style=travel_style,
            transport=transport,
            interests=list(interests),
        )

        # ----------------------------------------------------------------
        # Stage: User Profile (UserProfileEngine — not a separate agent)
        # ----------------------------------------------------------------
        t0 = time.monotonic()
        preferences: UserPreferences
        try:
            preferences = await self._profiles.get_preferences(user_id)
            ctx.food_preference = preferences.food_preference or "no_preference"
            ctx.accommodation = preferences.accommodation or "hotel"
            ctx.profile_interests = list(preferences.interests or [])
            ctx.profile_transport = preferences.transport or "any"
            profile_status = "ok"
            profile_summary = (
                f"Food: {ctx.food_preference}, "
                f"Interests: {', '.join(ctx.profile_interests[:5]) or 'none'}, "
                f"Style: {travel_style}"
            )
        except Exception as exc:
            logger.warning("SCIF_ORCHESTRATOR profile retrieval failed: %s", exc)
            preferences = UserPreferences()
            profile_status = "error"
            profile_summary = f"Profile retrieval failed: {exc}"

        ctx.add_stage(PipelineStage(
            stage_name="PROFILE_LOAD",
            component="UserProfileEngine",
            status=profile_status,
            summary=profile_summary,
            latency_ms=(time.monotonic() - t0) * 1000,
            data_source="Firestore/users",
        ))

        # ----------------------------------------------------------------
        # NavigationAgent — destination coordinates
        # ----------------------------------------------------------------
        t0 = time.monotonic()
        lat, lon, nav_constraints, nav_output = await self._navigation.resolve_destination(
            destination=destination,
            transport=transport or ctx.profile_transport,
        )
        ctx.lat = lat
        ctx.lon = lon
        ctx.geocode_source = "Geoapify" if lat is not None else "unavailable"
        ctx.add_agent_output(nav_output)
        ctx.add_stage(PipelineStage(
            stage_name="GEOCODING",
            component="NavigationAgent",
            status=nav_output.status,
            summary=nav_output.contribution_summary,
            latency_ms=(time.monotonic() - t0) * 1000,
            items=1 if lat is not None else 0,
            data_source="Geoapify",
        ))

        # ----------------------------------------------------------------
        # MemoryAgent — persistent user memory (Firestore)
        # ----------------------------------------------------------------
        t0 = time.monotonic()
        base_query = (
            f"Trip to {destination} for {num_days} days, "
            f"budget {budget} {currency}, "
            f"style {travel_style}, "
            f"interests: {', '.join(interests) or 'general'}"
        )
        memory_ctx, memory_output = await self._memory.retrieve(
            user_id=user_id,
            query=base_query,
        )
        if memory_ctx:
            ctx.memory_items = len(memory_ctx.relevant_preferences)
            ctx.memory_summary = memory_ctx.as_prompt_context()
            ctx.memory_preferences = [
                (p.value if hasattr(p, "value") else str(p))
                for p in memory_ctx.relevant_preferences[:10]
            ]
            if hasattr(memory_ctx, "behavioral") and memory_ctx.behavioral:
                ctx.memory_feature_weights = (
                    memory_ctx.behavioral.feature_weights or {}
                )
        ctx.add_agent_output(memory_output)
        ctx.add_stage(PipelineStage(
            stage_name="MEMORY_RETRIEVAL",
            component="MemoryAgent",
            status=memory_output.status,
            summary=memory_output.contribution_summary,
            latency_ms=(time.monotonic() - t0) * 1000,
            items=ctx.memory_items,
            data_source="Firestore/memory_longterm",
        ))

        # ----------------------------------------------------------------
        # WeatherAgent — Open-Meteo forecast for travel dates
        # ----------------------------------------------------------------
        t0 = time.monotonic()
        live_ctx, weather_constraints, weather_output = (
            await self._weather.fetch_and_constrain(
                destination=destination,
                lat=lat,
                lon=lon,
                start_date=start_date,
                end_date=end_date,
            )
        )
        ctx.live_context = live_ctx
        ctx.weather_constraints = weather_constraints
        ctx.add_agent_output(weather_output)
        ctx.add_stage(PipelineStage(
            stage_name="WEATHER_FETCH",
            component="WeatherAgent",
            status=weather_output.status,
            summary=weather_output.contribution_summary,
            latency_ms=(time.monotonic() - t0) * 1000,
            items=len(live_ctx.weather_by_date),
            data_source="Open-Meteo",
        ))

        # ----------------------------------------------------------------
        # BudgetAgent — deterministic budget analysis
        # ----------------------------------------------------------------
        t0 = time.monotonic()
        budget_ctx, budget_output = await self._budget.analyze(
            total_budget=budget,
            currency=currency,
            num_days=num_days,
            travel_style=travel_style,
        )
        ctx.budget_context = budget_ctx
        ctx.add_agent_output(budget_output)
        ctx.add_stage(PipelineStage(
            stage_name="BUDGET_ANALYSIS",
            component="BudgetAgent",
            status=budget_output.status,
            summary=budget_output.contribution_summary,
            latency_ms=(time.monotonic() - t0) * 1000,
            items=len(budget_ctx.constraints),
            data_source="internal_calculation",
        ))

        # ----------------------------------------------------------------
        # SafetyAgent — heuristic safety check
        # ----------------------------------------------------------------
        t0 = time.monotonic()
        _, safety_constraints, safety_output = await self._safety.pre_check(
            destination=destination,
            travel_style=travel_style,
            interests=interests,
        )
        ctx.add_agent_output(safety_output)
        ctx.add_stage(PipelineStage(
            stage_name="SAFETY_CHECK",
            component="SafetyAgent",
            status=safety_output.status,
            summary=safety_output.contribution_summary,
            latency_ms=(time.monotonic() - t0) * 1000,
            items=len(safety_constraints),
            data_source="internal_heuristic",
        ))

        # ----------------------------------------------------------------
        # SCIF PASS 1 — Derive final planning constraints
        # ----------------------------------------------------------------
        t0 = time.monotonic()
        scif_constraints = self._run_scif_pass1(
            ctx=ctx,
            nav_constraints=nav_constraints,
            safety_constraints=safety_constraints,
        )
        ctx.scif_constraints = scif_constraints

        ctx.add_stage(PipelineStage(
            stage_name="SCIF_PASS_1",
            component="SCIFOrchestrator",
            status="ok",
            summary=(
                f"SCIF Pass 1 complete. "
                f"Total constraints: {len(ctx.all_constraints())} "
                f"(weather={len(weather_constraints)}, "
                f"budget={len(budget_ctx.constraints)}, "
                f"navigation={len(nav_constraints)}, "
                f"safety={len(safety_constraints)}, "
                f"profile={len(scif_constraints)})."
            ),
            latency_ms=(time.monotonic() - t0) * 1000,
            items=len(ctx.all_constraints()),
            data_source="internal",
        ))

        total_latency_ms = (time.monotonic() - t_total) * 1000
        logger.info(
            "SCIF_ORCHESTRATOR_COMPLETE destination=%r "
            "agents=%d stages=%d constraints=%d latency_ms=%.0f",
            destination,
            len(ctx.agent_outputs),
            len(ctx.pipeline_stages),
            len(ctx.all_constraints()),
            total_latency_ms,
        )

        return ctx, preferences, memory_ctx

    def _run_scif_pass1(
        self,
        ctx: CognitivePlanningContext,
        nav_constraints: list[str],
        safety_constraints: list[str],
    ) -> list[str]:
        """
        SCIF Pass 1: derive profile-based and cross-agent constraints.

        This is the pre-generation pass where we analyze the combined
        outputs from all agents and produce actionable constraints for Qwen.

        Returns only PROFILE-DERIVED constraints (weather, budget, navigation,
        and safety constraints are already stored separately in ctx).
        These are merged into ctx.all_constraints() for prompt injection.
        """
        constraints: list[str] = []

        # --- Add navigation + safety constraints to scif_constraints ---
        # (they go through SCIF Pass 1 as part of the convergence)
        constraints.extend(nav_constraints)
        constraints.extend(safety_constraints)

        # --- Profile-derived constraints ---
        food_pref = ctx.food_preference or "no_preference"
        if food_pref not in ("no_preference", "any", "none", ""):
            if "vegetarian" in food_pref.lower():
                constraints.append(
                    "FOOD REQUIREMENT: User is vegetarian. ALL meal activities MUST use "
                    "vegetarian restaurants. Do NOT recommend meat dishes or non-vegetarian eateries."
                )
            elif "vegan" in food_pref.lower():
                constraints.append(
                    "FOOD REQUIREMENT: User is vegan. ALL meal activities MUST use "
                    "vegan-friendly restaurants only."
                )
            elif "halal" in food_pref.lower():
                constraints.append(
                    "FOOD REQUIREMENT: User requires halal food. Use halal-certified restaurants."
                )
            elif "jain" in food_pref.lower():
                constraints.append(
                    "FOOD REQUIREMENT: User follows Jain diet. Avoid root vegetables and non-Jain food."
                )
            else:
                constraints.append(
                    f"FOOD PREFERENCE: User prefers {food_pref} cuisine/restaurants."
                )

        # --- Interest-based constraints ---
        all_interests = list(dict.fromkeys(
            ctx.interests + ctx.profile_interests
        ))
        if all_interests:
            constraints.append(
                f"USER INTERESTS: Prioritize activities related to: "
                f"{', '.join(all_interests[:8])}. "
                f"Ensure at least one activity per day aligns with these interests."
            )

        # --- Travel style constraints ---
        style = ctx.travel_style or "balanced"
        if style == "relaxed":
            constraints.append(
                "TRAVEL STYLE — RELAXED: Plan 3–4 activities per day maximum. "
                "Include rest time. Avoid rushing between sites."
            )
        elif style == "adventure":
            constraints.append(
                "TRAVEL STYLE — ADVENTURE: Include outdoor, active, and exploratory activities. "
                "Hiking, nature walks, and adventure sports are preferred."
            )
        elif style == "luxury":
            constraints.append(
                "TRAVEL STYLE — LUXURY: Recommend premium experiences, upscale dining, and "
                "exclusive venues. Comfort and quality over quantity."
            )
        elif style == "budget":
            constraints.append(
                "TRAVEL STYLE — BUDGET: Maximize free and low-cost experiences. "
                "Prefer street food and local markets over expensive restaurants."
            )
        elif style == "cultural":
            constraints.append(
                "TRAVEL STYLE — CULTURAL: Prioritize museums, heritage sites, local traditions, "
                "festivals, and authentic cultural experiences."
            )

        # --- Memory-derived constraints ---
        if ctx.memory_preferences:
            top_prefs = ctx.memory_preferences[:3]
            constraints.append(
                f"LEARNED PREFERENCES (from past trips): {'; '.join(top_prefs)}. "
                f"Weight these in activity selection."
            )

        # --- Behavioral weights --- (only if meaningful deviation from defaults)
        fw = ctx.memory_feature_weights
        if fw:
            if fw.get("crowd_aversion", 0.0) > 0.3:
                constraints.append(
                    "BEHAVIORAL SIGNAL: User has shown preference for less crowded venues. "
                    "Avoid peak-hour activities at popular tourist spots where possible."
                )
            if fw.get("novelty_seeking", 0.0) > 0.3:
                constraints.append(
                    "BEHAVIORAL SIGNAL: User enjoys discovering new and unique experiences. "
                    "Include at least one off-the-beaten-path activity per day."
                )
            if fw.get("pace_preference", 0.0) > 0.3:
                constraints.append(
                    "BEHAVIORAL SIGNAL: User prefers a fast-paced itinerary with more activities."
                )
            elif fw.get("pace_preference", 0.0) < -0.3:
                constraints.append(
                    "BEHAVIORAL SIGNAL: User prefers a slow-paced, relaxed itinerary."
                )

        return constraints
