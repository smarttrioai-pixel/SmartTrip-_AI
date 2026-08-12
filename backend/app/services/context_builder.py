"""
ContextBuilder for SmartTrip AI (SCIF Framework).

Builds the Retrieval -> Context -> LLM input for itinerary generation.
It does not call external services and does not fabricate place data.
"""
from __future__ import annotations

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
            "Create a practical day-by-day itinerary as ONE JSON object. "
            "Keep every description and reason to one short sentence. "
            "Do not invent factual place metadata such as ratings, addresses, "
            "coordinates, opening hours, images, reviews, or restaurant details; "
            "those are resolved later by the real Places provider.\n\n"
            "Every day should normally contain three meal slots when appropriate: "
            "breakfast, lunch, and dinner, plus useful sightseeing/activities. "
            "For meals, specify the local/regional food or cuisine and a "
            "food_query for the Places provider. Do not use generic names such "
            "as 'Local Restaurant' or 'Local Food'.\n\n"
            "Transport is a hard constraint. Never invent an airport transfer. "
            "Only include an airport/flight transfer when transport is 'flight' "
            "or the user explicitly supplied an airport/flight arrival. If "
            "transport is 'any' or unspecified, do not assume an arrival mode. "
            "Likewise, do not invent train/bus/car arrival events.\n\n"
            "Use chronological times within each day.\n\n"
            "Required JSON schema: "
            '{"days":[{"day_number":1,"title":"string","activities":['
            '{"time":"09:00 AM","title":"string","description":"1 sentence",'
            '"location":"destination or concise search hint","estimated_cost":0.0,'
            '"category":"meal|attraction|culture|nature|shopping|transport|other",'
            '"reason":"1 sentence",'
            '"meal_type":"breakfast|lunch|dinner|null",'
            '"food_query":"local food/restaurant search query|null"}]}],'
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
