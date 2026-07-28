"""Firestore document shapes for the AI chat feature.

Structure: chats/{chat_id} holds metadata, chats/{chat_id}/messages/{message_id}
holds each turn — a subcollection keeps message history paginated and cheap
to append to without rewriting the whole document.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

COLLECTION = "chats"
MESSAGES_SUBCOLLECTION = "messages"


@dataclass
class ChatMessage:
    id: str
    role: str  # "user" | "assistant"
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content, "created_at": self.created_at}

    @staticmethod
    def from_snapshot(doc_id: str, data: dict) -> "ChatMessage":
        return ChatMessage(
            id=doc_id,
            role=data["role"],
            content=data["content"],
            created_at=data.get("created_at", datetime.now(timezone.utc)),
        )
