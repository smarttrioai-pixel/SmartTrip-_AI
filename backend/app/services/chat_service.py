"""
Business logic for the AI Chat assistant.
Connects chat interaction to MemoryEngine, Gemini AI, and LangGraph multi-agent context
for personalized conversational responses based on user memory and trip parameters.
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
    def __init__(self, chat_repository: ChatRepository, memory_engine: MemoryEngine | None = None) -> None:
        self._chats = chat_repository
        self._memory = memory_engine

    async def send_message(self, user_id: str, request: SendMessageRequest) -> SendMessageResponse:
        chat_id = request.chat_id or str(uuid.uuid4())
        await self._chats.ensure_chat(chat_id, user_id)

        history = await self._chats.get_history(chat_id)
        await self._chats.add_message(chat_id, "user", request.message)

        # Inject Memory Engine Context
        user_prompt = request.message
        if self._memory:
            try:
                mem_context = await self._memory.get_context(user_id, request.message, chat_id=chat_id)
                mem_text = mem_context.as_prompt_context()
                if mem_text:
                    user_prompt = f"{mem_text}\n\nUser Question: {request.message}"
            except Exception as e:
                logger.warning("Memory context non-fatal error in chat: %s", e)

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
