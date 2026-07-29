"""
Business logic for the AI Chat assistant.
Connects chat interaction to RetrievalEngine (Phase 5), MemoryEngine,
Gemini AI for personalized conversational responses based on multi-index
cognitive memory retrieval (user preferences + relevant destinations).

Phase 5: ChatService now uses RetrievalEngine.retrieve_for_chat() when
an engine is injected, giving Gemini both Memory (preferences, past
conversations) and Destination (relevant places) context in a structured
format.  Falls back to MemoryEngine.get_context() if no engine is set.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from app.cognitive.memory_engine import MemoryEngine
from app.core.gemini import generate_text
from app.repositories.chat_repository import ChatRepository
from app.schemas.chat import SendMessageRequest, SendMessageResponse

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are SmartTrip AI: an intelligent, memory-augmented travel assistant.
You possess deep knowledge of global destinations, local customs, itinerary optimization, packing, safety, and budget management.
Use the user's known preferences and travel memory provided in context to tailor your responses. Keep advice concise, actionable, and friendly."""

class ChatService:
    def __init__(
        self,
        chat_repository: ChatRepository,
        memory_engine: MemoryEngine | None = None,
        retrieval_engine=None,  # app.engines.RetrievalEngine | None  (Phase 5)
    ) -> None:
        self._chats = chat_repository
        self._memory = memory_engine
        self._retrieval = retrieval_engine

    async def send_message(self, user_id: str, request: SendMessageRequest) -> SendMessageResponse:
        chat_id = request.chat_id or str(uuid.uuid4())
        await self._chats.ensure_chat(chat_id, user_id)

        history = await self._chats.get_history(chat_id)
        await self._chats.add_message(chat_id, "user", request.message)

        # --- Phase 5: inject multi-index retrieval context ---
        user_prompt = request.message
        try:
            if self._retrieval is not None:
                # Richer context: Memory (preferences, past chats) + Destination (places)
                ctx = await self._retrieval.retrieve_for_chat(
                    user_id,
                    request.message,
                    chat_id,
                )
                ctx_text = ctx.as_prompt_text()
                if ctx_text:
                    user_prompt = f"{ctx_text}\n\nUser Question: {request.message}"
                    logger.debug(
                        "ChatService: RetrievalEngine context | intent=%s | docs=%d",
                        ctx.intent.value, ctx.total_documents_retrieved,
                    )
            elif self._memory is not None:
                # Legacy path: MemoryEngine only
                mem_context = await self._memory.get_context(
                    user_id, request.message, chat_id=chat_id
                )
                mem_text = mem_context.as_prompt_context()
                if mem_text:
                    user_prompt = f"{mem_text}\n\nUser Question: {request.message}"
        except Exception as e:
            logger.warning("Retrieval context non-fatal error in chat: %s", e)

        reply_text = await generate_text(
            system_prompt=SYSTEM_PROMPT,
            history=[{"role": m.role, "content": m.content} for m in history],
            user_prompt=user_prompt,
        )

        await self._chats.add_message(chat_id, "assistant", reply_text)
        return SendMessageResponse(chat_id=chat_id, reply=reply_text)

    async def get_history(self, chat_id: str) -> list[dict]:
        history = await self._chats.get_history(chat_id)
        return [{"role": m.role, "content": m.content} for m in history]

    async def list_chats(self, user_id: str) -> list[dict]:
        return await self._chats.list_chats_for_user(user_id)
