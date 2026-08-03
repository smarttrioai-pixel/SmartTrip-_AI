"""
ContextBuilder for SmartTrip AI (SCIF Framework).

Builds the enriched prompt context that is injected into every LLM call
made by the Planning Engine. This is the "Retrieval → Context → LLM"
layer specified in the architecture:

    Planning Engine
         ↓
    Retrieval Engine  (Memory, preferences, embeddings)
         ↓
    ContextBuilder    ← THIS MODULE
         ↓
    LLMService
         ↓
    Provider (HuggingFace / Gemma)

Responsibilities:
  - Merge the base trip request prompt with memory context
  - Merge retrieved user preferences and behavioral signal
  - Add any real-time context (weather, risk) that is computable at
    planning time without calling the LLM
  - Return a single enriched (system_prompt, user_prompt) tuple ready
    for LLMService.generate_json()

ContextBuilder is deliberately thin — it does not make LLM calls itself,
and it does not perform embedding or memory lookups. Those are done
upstream by the Retrieval Engine (MemoryEngine) before this is called.
"""
from __future__ import annotations

from app.cognitive.memory_engine import MemoryContext
from app.schemas.trip import GenerateItineraryRequest
from app.models.user import UserPreferences


class ContextBuilder:
    """
    Assembles the enriched prompt sent to LLMService for trip planning.

    Accepts pre-fetched context objects (memory, preferences) so that
    this class has no I/O dependencies — it is pure transformation logic
    and is fully unit-testable without mocking network calls.
    """

    def build_planning_prompt(
        self,
        request: GenerateItineraryRequest,
        num_days: int,
        preferences: UserPreferences,
        memory_context: MemoryContext | None = None,
        risk_note: str = "",
    ) -> tuple[str, str]:
        """
        Build the (system_prompt, user_prompt) pair for itinerary generation.

        Args:
            request:        The validated itinerary generation request.
            num_days:       Number of trip days (pre-computed by caller).
            preferences:    The user's declared preferences.
            memory_context: Retrieved memory context (may be None if unavailable).
            risk_note:      Optional risk advisory string from RiskAssessmentEngine.

        Returns:
            A (system_prompt, user_prompt) tuple ready for LLMService.generate_json().
        """
        system_prompt = self._planning_system_prompt()
        user_prompt = self._build_user_prompt(
            request=request,
            num_days=num_days,
            preferences=preferences,
            memory_context=memory_context,
            risk_note=risk_note,
        )
        return system_prompt, user_prompt

    def build_chat_context(
        self,
        user_message: str,
        memory_context: MemoryContext | None = None,
    ) -> str:
        """
        Build the enriched user message for chat completion.

        Prepends retrieved memory context so the LLM has user-specific
        personalization without the caller needing to know the format.

        Args:
            user_message:   The raw user chat message.
            memory_context: Retrieved memory context (may be None).

        Returns:
            Enriched user message string ready for LLMService.chat().
        """
        if memory_context is None:
            return user_message
        mem_text = memory_context.as_prompt_context()
        if not mem_text:
            return user_message
        return f"{mem_text}\n\nUser Question: {user_message}"

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    @staticmethod
    def _planning_system_prompt() -> str:
        return (
            "You are an expert travel planner. Given a destination, date range, "
            "budget, currency, travel style, interests, and user memory context, "
            "produce a day-by-day itinerary. "
            "Respond with ONLY a JSON object of this exact shape, no prose:\n\n"
            "{\n"
            '  "days": [\n'
            "    {\n"
            '      "day_number": 1,\n'
            '      "title": "string",\n'
            '      "activities": [\n'
            "        {\n"
            '          "time": "e.g. 09:00 AM",\n'
            '          "title": "string",\n'
            '          "description": "1-2 sentences",\n'
            '          "location": "string",\n'
            '          "estimated_cost": 0.0\n'
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ],\n"
            '  "estimated_total_cost": 0.0\n'
            "}"
        )

    @staticmethod
    def _build_user_prompt(
        request: GenerateItineraryRequest,
        num_days: int,
        preferences: UserPreferences,
        memory_context: MemoryContext | None,
        risk_note: str,
    ) -> str:
        lines: list[str] = [
            f"Destination: {request.destination}",
            f"Trip length: {num_days} days ({request.start_date} to {request.end_date})",
            f"Budget: {request.budget} {request.currency}",
            f"Travel style: {request.travel_style}",
            f"Interests: {', '.join(request.interests) or 'general sightseeing'}",
        ]

        # Inject declared preference interests from UserProfileEngine
        if preferences.interests:
            lines.append(
                f"Declared preference interests: {', '.join(preferences.interests)}"
            )

        # Inject retrieved memory context (preferences + behavioral weights)
        if memory_context is not None:
            mem_text = memory_context.as_prompt_context()
            if mem_text:
                lines.append(f"\nUser memory context:\n{mem_text}")

        # Inject risk advisory if provided
        if risk_note:
            lines.append(f"\nRisk advisory: {risk_note}")

        return "\n".join(lines)
