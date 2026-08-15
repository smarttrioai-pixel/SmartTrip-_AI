"""
Travel Diary & Story Router for SmartTrip AI.

Phase 3B: /generate now looks up the real trip (verifying it belongs to
the requesting user) and calls LLMService with the trip's actual itinerary
data, instead of returning a templated fake journal. LLMService routes the
call through the active provider (HuggingFace by default). /export-pdf
remains an honest plain-text export (real PDF generation out of scope).

Gemini is NOT called here. The LLMService + Provider abstraction handles
all text generation. Gemini Vision is used only in /explore/analyze-landmark.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, get_llm_service, get_trip_repository
from app.repositories.trip_repository import TripRepository
from app.services.llm_service import LLMService

router = APIRouter(prefix="/diary", tags=["Travel Diary"])

DIARY_SYSTEM_PROMPT = """You are a travel journal writer. Given a real day-by-day \
itinerary, write a warm, specific travel diary entry per day, grounded in the \
actual activities listed (not generic filler). Respond with ONLY a JSON object:
{
  "title": "Evocative trip title",
  "daily_journal": [
    {"day": 1, "story": "2-3 sentence narrative referencing the actual activities", "highlights": ["activity title 1", "activity title 2"]}
  ],
  "ai_narrative_summary": "1-2 sentence overall trip summary"
}"""

class GenerateDiaryRequest(BaseModel):
    trip_id: str

def _budget_status(budget: float, estimated_cost: float) -> str:
    """A short, real status derived from actual trip numbers — not a
    fabricated 'On Target' shown regardless of the real figures."""
    if budget <= 0:
        return "No budget set"
    ratio = estimated_cost / budget
    if ratio <= 1.0:
        return "Within Budget"
    if ratio <= 1.15:
        return "Slightly Over Estimate"
    return "Over Budget"

@router.post("/generate", summary="Generate AI Travel Journal entry from a real trip")
async def generate_diary_entry(
    request: GenerateDiaryRequest,
    current_user: CurrentUser,
    trip_repository: Annotated[TripRepository, Depends(get_trip_repository)],
    llm_service: Annotated[LLMService, Depends(get_llm_service)],
) -> dict[str, Any]:
    trip = await trip_repository.get_by_id(request.trip_id)
    if trip is None or trip.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")

    itinerary_summary = "\n".join(
        f"Day {day.get('day_number')}: {day.get('title')} — "
        + ", ".join(a.get("title", "") for a in day.get("activities", []))
        for day in trip.days
    )
    user_prompt = f"Destination: {trip.destination}\n\nItinerary:\n{itinerary_summary}"

    try:
        ai_result = await llm_service.generate_json(
            system_prompt=DIARY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=2048,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    # Add the real calendar date per day (start_date + day offset) — the
    # frontend displays this; it's genuinely computable from the trip's
    # actual start_date, not something to fabricate or drop.
    try:
        trip_start = date.fromisoformat(trip.start_date)
    except ValueError:
        trip_start = None

    daily_journal = ai_result.get("daily_journal", [])
    for entry in daily_journal:
        if trip_start is not None:
            day_num = entry.get("day", 1)
            entry["date"] = (trip_start + timedelta(days=day_num - 1)).isoformat()
        else:
            entry["date"] = ""

    return {
        "trip_id": trip.id,
        "destination": trip.destination,
        "title": ai_result.get("title", f"Memories from {trip.destination}"),
        "daily_journal": daily_journal,
        "expense_summary": {
            "total_estimated_cost": trip.estimated_total_cost,
            "currency": trip.currency,
            "status": _budget_status(trip.budget, trip.estimated_total_cost),
            "note": "Estimated from the AI-generated itinerary, not tracked actual spending (Expense Tracker not yet built)",
        },
        "ai_narrative_summary": ai_result.get("ai_narrative_summary", ""),
    }

@router.get("/export-pdf/{trip_id}", summary="Export travel diary as a text summary")
async def export_diary_text(
    trip_id: str,
    current_user: CurrentUser,
    trip_repository: Annotated[TripRepository, Depends(get_trip_repository)],
) -> Response:
    """
    Exports a plain-text trip summary. Real PDF generation is not yet
    implemented (would require a library like reportlab/weasyprint) — this
    is honestly a .txt export, not a PDF pretending to be one.
    """
    trip = await trip_repository.get_by_id(trip_id)
    if trip is None or trip.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")

    lines = [f"SmartTrip AI — Travel Summary", f"Destination: {trip.destination}", ""]
    for day in trip.days:
        lines.append(f"Day {day.get('day_number')}: {day.get('title')}")
        for activity in day.get("activities", []):
            lines.append(f"  - {activity.get('time', '')}: {activity.get('title', '')}")
        lines.append("")

    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=SmartTrip_Diary_{trip_id}.txt"},
    )
