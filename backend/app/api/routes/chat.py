from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, get_chat_service
from app.schemas.chat import ChatMessageResponse, ChatSummary, SendMessageRequest, SendMessageResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["AI Chat"])


@router.post("/messages", response_model=SendMessageResponse)
async def send_message(
    payload: SendMessageRequest,
    current_user: CurrentUser,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
) -> SendMessageResponse:
    try:
        return await chat_service.send_message(current_user.id, payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/{chat_id}/messages", response_model=list[ChatMessageResponse])
async def get_history(
    chat_id: str,
    current_user: CurrentUser,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
) -> list[ChatMessageResponse]:
    return await chat_service.get_history(chat_id)


@router.get("", response_model=list[ChatSummary])
async def list_chats(
    current_user: CurrentUser,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
) -> list[ChatSummary]:
    return await chat_service.list_chats(current_user.id)
