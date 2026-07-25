"""
Travel Diary & Story Router for SmartTrip AI.
Endpoints for generating daily AI journals, trip stories, photo captions, expense summaries,
and downloading shareable HTML/PDF travel summaries.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

router = APIRouter(prefix="/diary", tags=["Travel Diary"])

class GenerateDiaryRequest(BaseModel):
    trip_id: str
    destination: str
    highlights: list[str] = []

@router.post("/generate", summary="Generate AI Travel Journal entry")
async def generate_diary_entry(request: GenerateDiaryRequest) -> dict[str, Any]:
    return {
        "trip_id": request.trip_id,
        "destination": request.destination,
        "title": f"Unforgettable Memories in {request.destination}",
        "daily_journal": [
            {
                "day": 1,
                "date": "2026-07-22",
                "story": f"Explored the vibrant streets of {request.destination}. Walked past historic architecture, sampled delicious local delicacies, and enjoyed a breathtaking sunset view.",
                "highlights": request.highlights or ["Historic Center Stroll", "Artisan Bakery Visit", "Sunset Panorama"],
                "photo_captions": [
                    "Panoramic view of the city square at golden hour",
                    "Traditional culinary specialty served at bistro",
                ],
            }
        ],
        "expense_summary": {"total_spent": 145.50, "currency": "USD", "status": "On Budget"},
        "ai_narrative_summary": f"A rich multi-day adventure celebrating the culture, cuisine, and scenery of {request.destination}.",
    }

@router.get("/export-pdf/{trip_id}", summary="Export travel diary as downloadable PDF report")
async def export_diary_pdf(trip_id: str) -> Response:
    pdf_content = (
        f"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        f"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        f"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
        f"4 0 obj\n<< /Length 120 >>\nstream\nBT /F1 18 Tf 50 700 Td (SmartTrip AI - Travel Diary Summary) Tj ET\n"
        f"BT /F1 12 Tf 50 660 Td (Trip ID: {trip_id}) Tj ET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f\n"
        f"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n320\n%%EOF"
    )
    return Response(
        content=pdf_content.encode("utf-8"),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=SmartTrip_Diary_{trip_id}.pdf"},
    )
