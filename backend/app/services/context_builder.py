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
    Provider (Groq → Qwen3)

Responsibilities:
  - Merge the base trip request prompt with memory context
  - Merge retrieved user preferences and behavioral signal
  - Return a single enriched (system_prompt, user_prompt) tuple ready
    for LLMService.generate_json()

Design constraints for Groq free-tier (qwen/qwen3.6-27b):
  - System prompt is deliberately concise — the JSON schema is specified
    once, not repeated verbosely.
  - Activity descriptions must be 1 sentence max. Longer prompts consume
    more output tokens, pushing the response closer to the token budget
    ceiling and triggering finish_reason=length truncation.
  - Memory context is injected only if present (optional enrichment).
  - The prompt instructs the model to produce a USEFUL itinerary,
    not long historical essays.

ContextBuilder is deliberately thin — it does not make LLM calls itself,
and it does not perform embedding or memory lookups. Those are done
upstream by the Retrieval Engine (MemoryEngine) before this is called.
"""
from __future__ import annotations

from app.cognitive.memory_engine import MemoryContext
from app.schemas.trip import GenerateItineraryRequest
from app.models.user import UserPreferences

# Max_tokens to request from LLMService for trip itinerary generation.
# 6000 provides headroom for 7-day itineraries without hitting the Groq
# free-tier token-per-minute ceiling as hard as the previous 8000.
ITINERARY_MAX_TOKENS = 6000


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

        Returns:
            A (system_prompt, user_prompt) tuple ready for
            LLMService.generate_json(max_tokens=ITINERARY_MAX_TOKENS).
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
        """
        Concise system prompt optimised for Groq / Qwen3 free-tier.

        Keeps the schema description short so the model spends its token
        budget on content, not on repeating instructions back.
        """
        return (
            "You are a travel planner. Produce a day-by-day itinerary as a "
            "single JSON object. Be concise — each activity description must "
            "be 1 sentence. Do not write essays or historical backgrounds.\n\n"
            "Required JSON schema (output ONLY this, no prose):\n"
            '{"days":[{"day_number":1,"title":"string","activities":['
            '{"time":"09:00 AM","title":"string","description":"1 sentence.",'
            '"location":"string","estimated_cost":0.0,"category":"string",'
            '"reason":"1 sentence why this fits the user."}]}],'
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
        lines: list[str] = [
            f"Destination: {request.destination}",
            f"Duration: {num_days} days ({request.start_date} to {request.end_date})",
            f"Budget: {request.budget} {request.currency}",
            f"Travel style: {request.travel_style}",
            f"Interests: {', '.join(request.interests) if request.interests else 'general sightseeing'}",
        ]

        if preferences.interests:
            lines.append(
                f"User preference interests: {', '.join(preferences.interests)}"
            )

        if memory_context is not None:
            mem_text = memory_context.as_prompt_context()
            if mem_text:
                lines.append(f"User memory context: {mem_text}")

        if risk_note:
            lines.append(f"Risk note: {risk_note}")

        lines.append(
            "\nGenerate a practical, useful itinerary. "
            "Keep descriptions short (1 sentence each). "
            "Spread activities across the day (morning, afternoon, evening)."
        )

        return "\n".join(lines)
