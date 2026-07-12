from __future__ import annotations

import uuid
from datetime import datetime, timezone

from google.cloud.firestore import AsyncClient, Query

from app.models.chat import COLLECTION, MESSAGES_SUBCOLLECTION, ChatMessage


class ChatRepository:
    def __init__(self, db: AsyncClient) -> None:
        self._db = db
        self._chats = db.collection(COLLECTION)

    async def ensure_chat(self, chat_id: str, user_id: str) -> None:
        doc_ref = self._chats.document(chat_id)
        snapshot = await doc_ref.get()
        if not snapshot.exists:
            await doc_ref.set(
                {"user_id": user_id, "created_at": datetime.now(timezone.utc), "title": "New conversation"}
            )

    async def add_message(self, chat_id: str, role: str, content: str) -> ChatMessage:
        message = ChatMessage(id=str(uuid.uuid4()), role=role, content=content)
        messages = self._chats.document(chat_id).collection(MESSAGES_SUBCOLLECTION)
        await messages.document(message.id).set(message.to_dict())
        return message

    async def get_history(self, chat_id: str, *, limit: int = 30) -> list[ChatMessage]:
        messages = self._chats.document(chat_id).collection(MESSAGES_SUBCOLLECTION)
        query = messages.order_by("created_at", direction=Query.ASCENDING).limit_to_last(limit)

        history: list[ChatMessage] = []
        async for snapshot in query.stream():
            history.append(ChatMessage.from_snapshot(snapshot.id, snapshot.to_dict()))
        return history

    async def list_chats_for_user(self, user_id: str) -> list[dict]:
        query = self._chats.where("user_id", "==", user_id).order_by(
            "created_at", direction=Query.DESCENDING
        )
        chats: list[dict] = []
        async for snapshot in query.stream():
            data = snapshot.to_dict()
            chats.append({"id": snapshot.id, "title": data.get("title", "New conversation")})
        return chats
