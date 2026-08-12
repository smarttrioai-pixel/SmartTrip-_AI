from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    chat_id: str | None = Field(default=None, description="Omit to start a new conversation")
    message: str = Field(..., min_length=1, max_length=4000)


class ChatMessageResponse(BaseModel):
    role: str
    content: str


class SendMessageResponse(BaseModel):
    chat_id: str
    reply: str


class ChatSummary(BaseModel):
    id: str
    title: str
