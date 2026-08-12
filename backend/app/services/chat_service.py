"""
Business logic for the AI Chat assistant.

Connects chat interaction to MemoryEngine (retrieval) and LLMService
(text generation via Groq → qwen/qwen3-32b).

Architecture:
    ChatService
         ↓
    MemoryEngine.get_context()   ← Retrieval Engine
         ↓
    ContextBuilder.build_chat_context()
         ↓
    LLMService.chat()            ← Provider abstraction
         ↓
    GroqProvider (Groq Inference API → qwen/qwen3-32b)

No direct Gemini calls. Vision stays in GeminiVisionService.
"""
from __future__ import annotations

import logging
import uuid

from app.cognitive.memory_engine import MemoryEngine
from app.repositories.chat_repository import ChatRepository
from app.schemas.chat import SendMessageRequest, SendMessageResponse
from app.services.context_builder import ContextBuilder
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are SmartTrip AI: an intelligent, memory-augmented travel assistant. "
    "You possess deep knowledge of global destinations, local customs, "
    "itinerary optimization, packing, safety, and budget management. "
    "Use the user's known preferences and travel memory provided in context "
    "to tailor your responses. Keep advice concise, actionable, and friendly."
)


class ChatService:
    def __init__(
        self,
        chat_repository: ChatRepository,
        memory_engine: MemoryEngine | None = None,
        *,
        llm_service: LLMService,
        context_builder: ContextBuilder,
    ) -> None:
        self._chats = chat_repository
        self._memory = memory_engine
        self._llm = llm_service
        self._context_builder = context_builder

    async def send_message(self, user_id: str, request: SendMessageRequest) -> SendMessageResponse:
        chat_id = request.chat_id or str(uuid.uuid4())
        await self._chats.ensure_chat(chat_id, user_id)

        history = await self._chats.get_history(chat_id)
        await self._chats.add_message(chat_id, "user", request.message)

        # ------------------------------------------------------------------
        # Retrieval: Inject Memory Engine Context
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
        # Context Builder: assemble enriched user prompt
        # ------------------------------------------------------------------
        enriched_prompt = self._context_builder.build_chat_context(
            user_message=request.message,
            memory_context=memory_context,
        )

        # LLMService → GroqProvider → qwen/qwen3-32b
        reply_text = await self._llm.chat(
            system_prompt=SYSTEM_PROMPT,
            history=[{"role": m.role, "content": m.content} for m in history],
            user_prompt=enriched_prompt,
            max_tokens=1024,
        )

        await self._chats.add_message(chat_id, "assistant", reply_text)
        return SendMessageResponse(chat_id=chat_id, reply=reply_text)

    async def get_history(self, chat_id: str) -> list[dict]:
        history = await self._chats.get_history(chat_id)
        return [{"role": m.role, "content": m.content} for m in history]

    async def list_chats(self, user_id: str) -> list[dict]:
        return await self._chats.list_chats_for_user(user_id)
