from pydantic import BaseModel, Field
from typing import Any


class SendMessageRequest(BaseModel):
    chat_id: str | None = Field(default=None, description="Omit to start a new conversation")
    message: str = Field(..., min_length=1, max_length=4000)
    trip_id: str | None = Field(
        default=None,
        description="Active trip ID — injects current itinerary as context",
    )


class ChatMessageResponse(BaseModel):
    role: str
    content: str


class SendMessageResponse(BaseModel):
    chat_id: str
    reply: str
    action: dict[str, Any] | None = None  # structured itinerary action, if suggested by AI


class ChatSummary(BaseModel):
    id: str
    title: str

