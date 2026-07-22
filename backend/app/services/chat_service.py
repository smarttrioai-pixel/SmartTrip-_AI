"""
Business logic for the AI Chat assistant — the conversational half of the
"AI Tourist Guide" module (voice/text Q&A). Landmark recognition via the
camera is a separate Computer Vision service, not implemented in this pass.
"""
from __future__ import annotations

import uuid

from app.core.gemini import generate_text
from app.repositories.chat_repository import ChatRepository
from app.schemas.chat import SendMessageRequest, SendMessageResponse

SYSTEM_PROMPT = """You are the SmartTrip AI assistant: a knowledgeable, \
friendly travel companion. Help with itinerary questions, local customs, \
budgeting, packing, and on-the-ground advice. Keep answers concise and \
practical. If asked about a specific landmark, include its history, \
opening hours if commonly known, and nearby food/photo-spot suggestions \
when relevant."""


class ChatService:
    def __init__(self, chat_repository: ChatRepository) -> None:
        self._chats = chat_repository

    async def send_message(self, user_id: str, request: SendMessageRequest) -> SendMessageResponse:
        chat_id = request.chat_id or str(uuid.uuid4())
        await self._chats.ensure_chat(chat_id, user_id)

        history = await self._chats.get_history(chat_id)
        await self._chats.add_message(chat_id, "user", request.message)

        reply_text = await generate_text(
            system_prompt=SYSTEM_PROMPT,
            history=[{"role": m.role, "content": m.content} for m in history],
            user_prompt=request.message,
        )

        await self._chats.add_message(chat_id, "assistant", reply_text)
        return SendMessageResponse(chat_id=chat_id, reply=reply_text)

    async def get_history(self, chat_id: str) -> list[dict]:
        history = await self._chats.get_history(chat_id)
        return [{"role": m.role, "content": m.content} for m in history]

    async def list_chats(self, user_id: str) -> list[dict]:
        return await self._chats.list_chats_for_user(user_id)
