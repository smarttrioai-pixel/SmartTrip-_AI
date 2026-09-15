"""
Business logic for the AI Chat assistant.

Connects chat interaction to MemoryEngine (retrieval), TripRepository (trip context),
and LLMService (text generation via OpenAI by default).

Architecture:
    ChatService
         ↓
    TripRepository.get_by_id()    ← Current trip itinerary context (if trip_id given)
    MemoryEngine.get_context()    ← Long-term memory retrieval
         ↓
    ContextBuilder.build_chat_context()
         ↓
    LLMService.chat()             ← Provider abstraction (OpenAI / Groq)

The LLM can signal structured actions (e.g., replace_activity) via [ACTION: ...] tags.
These are extracted and returned to the caller for routing to ItineraryModifier.
No direct Firestore writes from the LLM.
"""
from __future__ import annotations

import logging
import re
import uuid

from app.cognitive.memory_engine import MemoryEngine
from app.repositories.chat_repository import ChatRepository
from app.repositories.trip_repository import TripRepository
from app.schemas.chat import SendMessageRequest, SendMessageResponse
from app.services.context_builder import ContextBuilder
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are SmartTrip AI: an intelligent, memory-augmented travel assistant. "
    "You possess deep knowledge of global destinations, local customs, "
    "itinerary optimization, packing, safety, and budget management. "
    "Use the user's known preferences, travel memory, and current trip itinerary "
    "provided in context to tailor your responses. "
    "Keep advice concise, actionable, and friendly.\n\n"
    "If the user asks to change their itinerary (e.g., 'remove the museum', "
    "'replace the restaurant', 'move the temple visit'), you may suggest a change "
    "by ending your response with exactly one action tag on its own line:\n"
    "[ACTION: {\"action\": \"replace_activity\", ...}]\n"
    "Only include an action tag if you are confident the user wants a specific "
    "itinerary modification. Never fabricate activity IDs."
)


class ChatService:
    def __init__(
        self,
        chat_repository: ChatRepository,
        memory_engine: MemoryEngine | None = None,
        *,
        llm_service: LLMService,
        context_builder: ContextBuilder,
        trip_repository: TripRepository | None = None,
    ) -> None:
        self._chats = chat_repository
        self._memory = memory_engine
        self._llm = llm_service
        self._context_builder = context_builder
        self._trips = trip_repository

    async def send_message(
        self,
        user_id: str,
        request: SendMessageRequest,
    ) -> SendMessageResponse:
        chat_id = request.chat_id or str(uuid.uuid4())
        await self._chats.ensure_chat(chat_id, user_id)

        history = await self._chats.get_history(chat_id)
        await self._chats.add_message(chat_id, "user", request.message)

        # ------------------------------------------------------------------
        # Retrieval 1: Long-term memory context
        # ------------------------------------------------------------------
        memory_context = None
        if self._memory:
            try:
                memory_context = await self._memory.get_context(
                    user_id, request.message, chat_id=chat_id
                )
            except Exception as e:
                logger.warning("Memory context non-fatal error in chat: %s", e)

        # ------------------------------------------------------------------
        # Retrieval 2: Current trip itinerary (if trip_id provided)
        # ------------------------------------------------------------------
        trip_context_str = ""
        trip_id = getattr(request, "trip_id", None)
        if trip_id and self._trips:
            try:
                trip = await self._trips.get_by_id(trip_id)
                if trip and trip.user_id == user_id:
                    trip_context_str = self._build_trip_context(trip)
            except Exception as e:
                logger.warning("Trip context non-fatal error in chat: %s", e)

        # ------------------------------------------------------------------
        # Context Builder: assemble enriched prompt
        # ------------------------------------------------------------------
        enriched_prompt = self._context_builder.build_chat_context(
            user_message=request.message,
            memory_context=memory_context,
        )

        # Prepend trip context if available
        if trip_context_str:
            enriched_prompt = (
                f"[CURRENT TRIP ITINERARY]\n{trip_context_str}\n\n"
                f"[USER MESSAGE]\n{enriched_prompt}"
            )

        # ------------------------------------------------------------------
        # LLMService → OpenAIProvider (or GroqProvider as fallback)
        # ------------------------------------------------------------------
        reply_text = await self._llm.chat(
            system_prompt=SYSTEM_PROMPT,
            history=[{"role": m.role, "content": m.content} for m in history],
            user_prompt=enriched_prompt,
            max_tokens=1024,
        )

        # ------------------------------------------------------------------
        # Extract any structured action tag from the reply
        # ------------------------------------------------------------------
        action_tag, clean_reply = self._extract_action(reply_text)

        await self._chats.add_message(chat_id, "assistant", clean_reply)
        return SendMessageResponse(
            chat_id=chat_id,
            reply=clean_reply,
            action=action_tag,
        )

    async def get_history(self, chat_id: str) -> list[dict]:
        history = await self._chats.get_history(chat_id)
        return [{"role": m.role, "content": m.content} for m in history]

    async def list_chats(self, user_id: str) -> list[dict]:
        return await self._chats.list_chats_for_user(user_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_trip_context(self, trip) -> str:
        """Build a concise itinerary summary for the LLM context."""
        lines = [
            f"Destination: {trip.destination}",
            f"Dates: {trip.start_date} to {trip.end_date}",
            f"Budget: {trip.budget} {trip.currency}",
            f"Style: {trip.travel_style}",
        ]
        for day in trip.days:
            lines.append(f"\nDay {day.get('day_number')}: {day.get('title', '')}")
            for act in day.get("activities", []):
                lines.append(
                    f"  [{act.get('id', act.get('title', '')[:15])}] "
                    f"{act.get('time', '')} — {act.get('title', '')} "
                    f"({act.get('category', '')})"
                )
        return "\n".join(lines)

    @staticmethod
    def _extract_action(reply_text: str) -> tuple[dict | None, str]:
        """
        Extract structured [ACTION: {...}] tag from end of reply.
        Returns (action_dict, clean_reply_without_tag).
        """
        import json
        pattern = r"\[ACTION:\s*(\{.*?\})\]"
        match = re.search(pattern, reply_text, re.DOTALL)
        if match:
            try:
                action = json.loads(match.group(1))
                clean = reply_text[: match.start()].strip()
                return action, clean
            except Exception:
                pass
        return None, reply_text
