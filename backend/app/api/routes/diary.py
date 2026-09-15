from __future__ import annotations

from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, Response, status, UploadFile, File, Form
from pydantic import BaseModel

from app.api.deps import CurrentUser, get_diary_service
from app.services.diary_service import DiaryService

router = APIRouter(prefix="/diary", tags=["Travel Diary"])

class CreateEntryRequest(BaseModel):
    date: str
    data: dict = {}

class NoteRequest(BaseModel):
    note: str

class ExpenseRequest(BaseModel):
    name: str
    amount: float
    currency: str

class PlaceRequest(BaseModel):
    place: str

class GenerateStoryRequest(BaseModel):
    writing_style: str = "journal"

@router.get("/{trip_id}/entries", summary="Get all diary entries")
async def get_entries(
    trip_id: str,
    current_user: CurrentUser,
    diary_service: Annotated[DiaryService, Depends(get_diary_service)],
) -> list[dict]:
    return await diary_service.get_entries(trip_id, current_user.id)

@router.post("/{trip_id}/entries", summary="Create or update entry for a date")
async def create_entry(
    trip_id: str,
    request: CreateEntryRequest,
    current_user: CurrentUser,
    diary_service: Annotated[DiaryService, Depends(get_diary_service)],
) -> dict:
    return await diary_service.get_or_create_entry(trip_id, request.date, current_user.id)

@router.post("/{trip_id}/entries/{id}/note", summary="Add note")
async def add_note(
    trip_id: str,
    id: str,
    request: NoteRequest,
    current_user: CurrentUser,
    diary_service: Annotated[DiaryService, Depends(get_diary_service)],
) -> dict:
    return await diary_service.add_note(trip_id, id, current_user.id, request.note)

@router.post("/{trip_id}/entries/{id}/expense", summary="Add expense")
async def add_expense(
    trip_id: str,
    id: str,
    request: ExpenseRequest,
    current_user: CurrentUser,
    diary_service: Annotated[DiaryService, Depends(get_diary_service)],
) -> dict:
    return await diary_service.add_expense(trip_id, id, current_user.id, request.name, request.amount, request.currency)

@router.post("/{trip_id}/entries/{id}/place", summary="Add place visited")
async def add_place(
    trip_id: str,
    id: str,
    request: PlaceRequest,
    current_user: CurrentUser,
    diary_service: Annotated[DiaryService, Depends(get_diary_service)],
) -> dict:
    return await diary_service.add_place_visited(trip_id, id, current_user.id, request.place)

@router.post("/{trip_id}/entries/{id}/photo", summary="Upload and analyze photo")
async def upload_photo(
    trip_id: str,
    id: str,
    current_user: CurrentUser,
    diary_service: Annotated[DiaryService, Depends(get_diary_service)],
    file: UploadFile = File(None),
    image_b64: str = Form(None),
) -> dict:
    if not file and not image_b64:
        raise HTTPException(status_code=400, detail="Must provide file or image_b64")
        
    image_bytes = None
    if file:
        image_bytes = await file.read()
        
    return await diary_service.analyze_photo_and_add(trip_id, id, current_user.id, image_bytes, image_b64)

@router.post("/{trip_id}/entries/{id}/generate", summary="Generate AI day story")
async def generate_day_story(
    trip_id: str,
    id: str,
    request: GenerateStoryRequest,
    current_user: CurrentUser,
    diary_service: Annotated[DiaryService, Depends(get_diary_service)],
) -> dict:
    return await diary_service.generate_day_story(trip_id, id, current_user.id, request.writing_style)

@router.put("/{trip_id}/entries/{id}", summary="Update entry")
async def update_entry(
    trip_id: str,
    id: str,
    request: dict,
    current_user: CurrentUser,
    diary_service: Annotated[DiaryService, Depends(get_diary_service)],
) -> dict:
    return await diary_service._diary.update_entry(trip_id, id, current_user.id, request)

@router.get("/{trip_id}/story", summary="Get trip story")
async def get_trip_story(
    trip_id: str,
    current_user: CurrentUser,
    diary_service: Annotated[DiaryService, Depends(get_diary_service)],
) -> dict:
    story = await diary_service._diary.get_trip_story(trip_id, current_user.id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story

@router.post("/{trip_id}/story/generate", summary="Generate trip story")
async def generate_trip_story(
    trip_id: str,
    current_user: CurrentUser,
    diary_service: Annotated[DiaryService, Depends(get_diary_service)],
) -> dict:
    return await diary_service.generate_trip_story(trip_id, current_user.id)

@router.get("/{trip_id}/export-pdf", summary="Export PDF")
async def export_pdf(
    trip_id: str,
    current_user: CurrentUser,
    diary_service: Annotated[DiaryService, Depends(get_diary_service)],
) -> Response:
    pdf_bytes = await diary_service.export_pdf(trip_id, current_user.id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=SmartTrip_Diary_{trip_id}.pdf"},
    )
