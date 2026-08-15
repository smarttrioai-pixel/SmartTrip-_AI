"""
ContextBuilder for SmartTrip AI (SCIF Framework).

Builds the Retrieval → Context → LLM input for itinerary generation.
It does not call external services and does not fabricate place data.

Enhanced (live context):
    build_planning_prompt_with_context() — extends build_planning_prompt()
    by injecting verified live travel conditions (weather, SCIF decisions)
    into the Qwen prompt. Live data comes from LiveContextEngine, not LLM.

    Qwen must NOT be told to infer or guess live conditions — it receives
    verified facts. If a condition is unavailable, it is either omitted or
    explicitly stated as unavailable so Qwen plans conservatively.
"""
from __future__ import annotations

from app.cognitive.live_context import CognitiveContext
from app.cognitive.memory_engine import MemoryContext
from app.schemas.trip import GenerateItineraryRequest
from app.models.user import UserPreferences

ITINERARY_MAX_TOKENS = 4500


class ContextBuilder:
    def build_planning_prompt(
        self,
        request: GenerateItineraryRequest,
        num_days: int,
        preferences: UserPreferences,
        memory_context: MemoryContext | None = None,
        risk_note: str = "",
    ) -> tuple[str, str]:
        return (
            self._planning_system_prompt(),
            self._build_user_prompt(
                request, num_days, preferences, memory_context, risk_note
            ),
        )

    def build_planning_prompt_with_context(
        self,
        request: GenerateItineraryRequest,
        num_days: int,
        preferences: UserPreferences,
        memory_context: MemoryContext | None = None,
        cognitive_context: CognitiveContext | None = None,
        risk_note: str = "",
    ) -> tuple[str, str]:
        """
        Extended planning prompt that injects verified live context
        (weather, SCIF decisions) into the Qwen user prompt.

        Live conditions section is injected ONLY when real data exists.
        Never injects fabricated or assumed conditions.
        """
        system_prompt = self._planning_system_prompt()
        user_prompt = self._build_user_prompt(
            request, num_days, preferences, memory_context, risk_note
        )
        if cognitive_context is not None:
            live_section = self._build_live_context_section(cognitive_context)
            if live_section:
                user_prompt = user_prompt + "\n\n" + live_section
        return system_prompt, user_prompt

    def build_chat_context(
        self,
        user_message: str,
        memory_context: MemoryContext | None = None,
    ) -> str:
        if memory_context is None:
            return user_message
        mem_text = memory_context.as_prompt_context()
        return f"{mem_text}\n\nUser Question: {user_message}" if mem_text else user_message

    @staticmethod
    def _planning_system_prompt() -> str:
        return (
            "You are the itinerary planning component of SmartTrip AI. "
            "Your ONLY job is to output a PLANNING INTENT — a structured day-by-day "
            "schedule of what to do, when, and why. "
            "You do NOT know actual place names, addresses, ratings, or opening hours. "
            "The Places API will find real places after you generate the intent.\n\n"
            "CRITICAL RULES:\n"
            "1. Do NOT output real place names as titles. Output what KIND of place "
            "   you want (slot_intent) and a search query (place_query).\n"
            "2. Do NOT invent addresses, coordinates, ratings, reviews, or images.\n"
            "3. For meals: specify the LOCAL FOOD TYPE and a food_query. "
            "   Do not use generic names like 'Local Restaurant' or 'Central Plaza'.\n"
            "4. Transport is a hard constraint. Only include an airport/flight "
            "   transfer when transport is 'flight'. Never assume arrivals by air.\n"
            "5. LIVE CONDITIONS: When provided below, treat them as verified external "
            "   facts. Respect rain constraints.\n\n"
            "For attraction slots, plan these types where appropriate:\n"
            "  - historical temples/shrines (place_type_hint: hindu_temple)\n"
            "  - historical landmarks (place_type_hint: historical_landmark)\n"
            "  - museums (place_type_hint: museum)\n"
            "  - parks/nature (place_type_hint: national_park)\n"
            "  - art/cultural centres (place_type_hint: cultural_center)\n\n"
            "For meal slots, plan 3 meals per day (breakfast, lunch, dinner) with "
            "cuisine intent specific to the DESTINATION — avoid generic names.\n\n"
            "Use chronological times within each day.\n\n"
            "Required JSON schema:\n"
            '{"days":[{"day_number":1,"title":"string","activities":['
            '{"time":"09:00 AM",'
            '"slot_intent":"what kind of place/activity (e.g. ancient Hindu temple visit)",'
            '"place_query":"Google search query for real places (e.g. ancient temples Guntur)",'
            '"place_type_hint":"primary Google place type hint (e.g. hindu_temple)",'
            '"category":"attraction|culture|nature|museum|meal|transport|other",'
            '"meal_type":"breakfast|lunch|dinner|null",'
            '"food_query":"local food/cuisine search query for restaurants (e.g. Andhra tiffin breakfast Guntur)|null",'
            '"estimated_cost":0.0,'
            '"preferred_duration_minutes":90,'
            '"reason":"1 sentence why this fits the user"}]}],'
            '"estimated_total_cost":0.0}'
        )

    @staticmethod
    def _build_user_prompt(
        request: GenerateItineraryRequest,
        num_days: int,
        preferences: UserPreferences,
        memory_context: MemoryContext | None,
        risk_note: str,
    ) -> str:
        lines = [
            f"Destination: {request.destination}",
            f"Duration: {num_days} days ({request.start_date} to {request.end_date})",
            f"Budget: {request.budget} {request.currency}",
            f"Travel style: {request.travel_style}",
            f"Transport: {request.transport or 'any'}",
            f"Interests: {', '.join(request.interests) if request.interests else 'general sightseeing'}",
        ]
        if preferences.interests:
            lines.append(f"User preference interests: {', '.join(preferences.interests)}")
        if preferences.transport and preferences.transport != "any" and request.transport == "any":
            lines.append(f"Stored user transport preference: {preferences.transport}")
        if memory_context is not None:
            mem_text = memory_context.as_prompt_context()
            if mem_text:
                lines.append(f"User memory context: {mem_text}")
        if risk_note:
            lines.append(f"Risk note: {risk_note}")

        lines.append(
            "\nPlanning constraints: create exactly the requested number of days; "
            "keep activities concise; include breakfast, lunch and dinner where "
            "the day schedule permits; prioritize local cuisine; meals must include "
            "a useful food_query; do not invent an airport transfer unless air "
            "travel is explicitly confirmed; and keep each day's activities in "
            "chronological order."
        )
        return "\n".join(lines)

    @staticmethod
    def _build_live_context_section(cognitive_context: CognitiveContext) -> str:
        """
        Build the live conditions section injected into the Qwen prompt.

        Rules:
        - Only inject when real data is available.
        - Never claim weather is "Sunny" or "Clear" unless Open-Meteo confirmed it.
        - If unavailable, say explicitly: "Weather data unavailable."
        - SCIF reschedule decisions appear as hard constraints.
        - Source is always cited (open-meteo, geoapify).
        """
        lines: list[str] = []
        live = cognitive_context.live_context

        # Weather per day
        weather_lines: list[str] = []
        for d, snap in sorted(live.weather_by_date.items()):
            if snap.status == "available":
                temp_str = ""
                if snap.temperature_max is not None and snap.temperature_min is not None:
                    temp_str = f", {snap.temperature_min:.0f}–{snap.temperature_max:.0f}°C"
                rain_str = ""
                if snap.rain_probability is not None:
                    rain_str = f", rain probability {int(snap.rain_probability * 100)}%"
                weather_lines.append(
                    f"  {d.strftime('%b %d (%A)')}: {snap.condition}{temp_str}{rain_str}"
                    f" [source: open-meteo]"
                )

        if weather_lines:
            lines.append("=== VERIFIED LIVE WEATHER (do not override) ===")
            lines.extend(weather_lines)

        # Planning constraints derived from weather
        if cognitive_context.constraints:
            lines.append("")
            lines.append("=== SCIF PLANNING CONSTRAINTS (hard rules from live data) ===")
            for c in cognitive_context.constraints:
                lines.append(f"  CONSTRAINT: {c}")

        # SCIF reschedule decisions (inform Qwen of pre-decisions)
        reschedule_decisions = [
            d for d in cognitive_context.decisions
            if d.decision == "reschedule"
        ]
        if reschedule_decisions:
            lines.append("")
            lines.append("=== SCIF SCHEDULING DECISIONS ===")
            for dec in reschedule_decisions:
                line = f"  {dec.place}: {dec.reason}"
                if dec.suggested_time:
                    line += f" → Suggested time: {dec.suggested_time}"
                lines.append(line)

        if not lines:
            return ""

        lines.append("=== END LIVE CONDITIONS ===")
        return "\n".join(lines)
