from __future__ import annotations

import uuid
from datetime import datetime, timezone

from google.cloud.firestore import AsyncClient, Query, Increment

from app.models.chat import COLLECTION, MESSAGES_SUBCOLLECTION, ChatMessage


class ChatRepository:
    def __init__(self, db: AsyncClient) -> None:
        self._db = db
        self._chats = db.collection(COLLECTION)

    def _generate_title(self, message: str) -> str:
        """
        Generate a simple title from the first user message.
        Replace this later with Gemini for AI-generated titles.
        """
        title = " ".join(message.strip().split())

        if not title:
            return "New conversation"

        if len(title) > 40:
            return title[:40] + "..."

        return title

    async def ensure_chat(self, chat_id: str, user_id: str) -> None:
        doc_ref = self._chats.document(chat_id)

        snapshot = await doc_ref.get()

        if not snapshot.exists:
            now = datetime.now(timezone.utc)

            await doc_ref.set(
                {
                    "user_id": user_id,
                    "title": "New conversation",
                    "created_at": now,
                    "updated_at": now,
                    "message_count": 0,
                }
            )

    async def add_message(
        self,
        chat_id: str,
        role: str,
        content: str,
    ) -> ChatMessage:

        message = ChatMessage(
            id=str(uuid.uuid4()),
            role=role,
            content=content,
        )

        messages = (
            self._chats
            .document(chat_id)
            .collection(MESSAGES_SUBCOLLECTION)
        )

        await messages.document(message.id).set(message.to_dict())

        chat_ref = self._chats.document(chat_id)

        updates = {
            "updated_at": datetime.now(timezone.utc),
            "message_count": Increment(1),
        }

        # Auto title only from first user message
        if role == "user":
            snapshot = await chat_ref.get()
            data = snapshot.to_dict() or {}

            if data.get("title") == "New conversation":
                updates["title"] = self._generate_title(content)

        await chat_ref.update(updates)

        return message

    async def get_history(
        self,
        chat_id: str,
        *,
        limit: int = 30,
    ) -> list[ChatMessage]:

        messages = (
            self._chats
            .document(chat_id)
            .collection(MESSAGES_SUBCOLLECTION)
        )

        query = (
            messages
            .order_by("created_at", direction=Query.ASCENDING)
            .limit_to_last(limit)
        )

        history: list[ChatMessage] = []

        snapshots = await query.get()

        for snapshot in snapshots:
            history.append(
                ChatMessage.from_snapshot(
                    snapshot.id,
                    snapshot.to_dict(),
                )
            )

        return history

    async def list_chats_for_user(
        self,
        user_id: str,
    ) -> list[dict]:

        query = (
            self._chats
            .where("user_id", "==", user_id)
            .order_by("updated_at", direction=Query.DESCENDING)
        )

        chats: list[dict] = []

        async for snapshot in query.stream():
            data = snapshot.to_dict()

            chats.append(
                {
                    "id": snapshot.id,
                    "title": data.get("title", "New conversation"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "message_count": data.get("message_count", 0),
                }
            )

        return chats

    async def rename_chat(
        self,
        chat_id: str,
        title: str,
    ) -> None:

        await self._chats.document(chat_id).update(
            {
                "title": title.strip(),
                "updated_at": datetime.now(timezone.utc),
            }
        )

    async def clear_chat(
        self,
        chat_id: str,
    ) -> None:

        messages = (
            self._chats
            .document(chat_id)
            .collection(MESSAGES_SUBCOLLECTION)
        )

        snapshots = await messages.get()

        for snapshot in snapshots:
            await snapshot.reference.delete()

        await self._chats.document(chat_id).update(
            {
                "message_count": 0,
                "updated_at": datetime.now(timezone.utc),
            }
        )

    async def delete_chat(
        self,
        chat_id: str,
    ) -> None:

        chat_ref = self._chats.document(chat_id)

        messages = chat_ref.collection(MESSAGES_SUBCOLLECTION)

        snapshots = await messages.get()

        for snapshot in snapshots:
            await snapshot.reference.delete()

        await chat_ref.delete()
