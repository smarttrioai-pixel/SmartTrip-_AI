from __future__ import annotations

import base64
import io
import json
import logging
from datetime import datetime, timezone

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from app.repositories.diary_repository import DiaryRepository
from app.repositories.trip_repository import TripRepository
from app.services.llm_service import LLMService
from app.core.gemini import generate_json_from_image

logger = logging.getLogger(__name__)

class DiaryService:
    def __init__(
        self,
        diary_repo: DiaryRepository,
        trip_repo: TripRepository,
        llm_service: LLMService,
        gemini_provider,
    ):
        self._diary = diary_repo
        self._trips = trip_repo
        self._llm = llm_service
        self._gemini = gemini_provider

    async def get_entries(self, trip_id: str, user_id: str) -> list[dict]:
        return await self._diary.get_entries(trip_id, user_id)

    async def get_or_create_entry(self, trip_id: str, date: str, user_id: str) -> dict:
        return await self._diary.create_or_update_entry(trip_id, user_id, date, {})

    async def add_note(self, trip_id: str, entry_id: str, user_id: str, note: str) -> dict:
        entry = await self._diary.get_entry(trip_id, entry_id, user_id)
        if not entry:
            raise ValueError("Entry not found")
        notes = entry.get("notes", [])
        notes.append(note)
        return await self._diary.update_entry(trip_id, entry_id, user_id, {"notes": notes})

    async def add_expense(self, trip_id: str, entry_id: str, user_id: str, name: str, amount: float, currency: str) -> dict:
        entry = await self._diary.get_entry(trip_id, entry_id, user_id)
        if not entry:
            raise ValueError("Entry not found")
        expenses = entry.get("expenses", [])
        expenses.append({"name": name, "amount": amount, "currency": currency})
        return await self._diary.update_entry(trip_id, entry_id, user_id, {"expenses": expenses})

    async def add_place_visited(self, trip_id: str, entry_id: str, user_id: str, place: str) -> dict:
        entry = await self._diary.get_entry(trip_id, entry_id, user_id)
        if not entry:
            raise ValueError("Entry not found")
        places = entry.get("places_visited", [])
        places.append(place)
        return await self._diary.update_entry(trip_id, entry_id, user_id, {"places_visited": places})

    async def analyze_photo_and_add(
        self, 
        trip_id: str, 
        entry_id: str, 
        user_id: str, 
        image_bytes: bytes,
        image_b64: str,
    ) -> dict:
        entry = await self._diary.get_entry(trip_id, entry_id, user_id)
        if not entry:
            raise ValueError("Entry not found")
            
        if not image_bytes and image_b64:
            image_bytes = base64.b64decode(image_b64)
            
        description = "Analysis unavailable"
        if image_bytes:
            try:
                system_prompt = (
                    "Analyze this travel photo. Return a JSON object with a single field 'description' "
                    "containing a short 1-2 sentence description of what is in the photo."
                )
                ai_data = await generate_json_from_image(
                    system_prompt=system_prompt, user_prompt="Describe this photo", image_bytes=image_bytes
                )
                description = ai_data.get("description", "Analysis unavailable")
            except Exception as e:
                logger.warning(f"Photo analysis failed: {e}")
                
        photo_obj = {
            "url": "",
            "gemini_description": description,
            "added_at": datetime.now(timezone.utc).isoformat()
        }
        
        photos = entry.get("photos", [])
        photos.append(photo_obj)
        return await self._diary.update_entry(trip_id, entry_id, user_id, {"photos": photos})

    async def generate_day_story(
        self,
        trip_id: str,
        entry_id: str,
        user_id: str,
        writing_style: str = "journal",
    ) -> dict:
        entry = await self._diary.get_entry(trip_id, entry_id, user_id)
        if not entry:
            raise ValueError("Entry not found")
            
        system_prompt = (
            f"Generate a {writing_style} travel diary entry based ONLY on the following actual data. "
            "Do not invent any places, events, or experiences not listed here. "
            "Return ONLY a JSON object with a single field 'story' containing the text."
        )
        
        user_prompt = (
            f"Date: {entry.get('date')}\n"
            f"Places visited: {', '.join(entry.get('places_visited', []))}\n"
            f"Notes: {', '.join(entry.get('notes', []))}\n"
            f"Expenses: {json.dumps(entry.get('expenses', []))}\n"
            f"Photo descriptions: {', '.join([p.get('gemini_description', '') for p in entry.get('photos', [])])}\n"
        )
        
        try:
            ai_data = await self._llm.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
            story = ai_data.get("story", "")
        except Exception as e:
            story = f"Story generation failed: {e}"
            
        return await self._diary.update_entry(trip_id, entry_id, user_id, {"ai_story": story, "writing_style": writing_style})

    async def generate_trip_story(self, trip_id: str, user_id: str) -> dict:
        trip = await self._trips.get_by_id(trip_id)
        entries = await self._diary.get_entries(trip_id, user_id)
        
        system_prompt = (
            "Generate an end-of-trip story from the provided diary entries and trip metadata. "
            "Only mention actual visited places and experiences from the diary entries. "
            "Return ONLY a JSON object with fields 'title' and 'story'."
        )
        
        all_places = []
        for e in entries:
            all_places.extend(e.get("places_visited", []))
            
        user_prompt = (
            f"Destination: {trip.destination if trip else 'Unknown'}\n"
            f"Total days: {len(entries)}\n"
            f"All places visited: {', '.join(all_places)}\n"
        )
        
        try:
            ai_data = await self._llm.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception:
            ai_data = {"title": "Trip Summary", "story": "Failed to generate story."}
            
        return await self._diary.save_trip_story(trip_id, user_id, ai_data)

    async def export_pdf(self, trip_id: str, user_id: str) -> bytes:
        trip = await self._trips.get_by_id(trip_id)
        entries = await self._diary.get_entries(trip_id, user_id)
        trip_story = await self._diary.get_trip_story(trip_id, user_id)
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []
        
        title = f"Travel Diary: {trip.destination if trip else 'Unknown'}"
        elements.append(Paragraph(title, styles['Title']))
        elements.append(Spacer(1, 12))
        
        if trip_story:
            elements.append(Paragraph(trip_story.get("title", "Trip Summary"), styles['Heading2']))
            elements.append(Paragraph(trip_story.get("story", ""), styles['Normal']))
            elements.append(Spacer(1, 12))
            
        for entry in entries:
            elements.append(Paragraph(f"Date: {entry.get('date', 'Unknown')}", styles['Heading2']))
            
            if entry.get("ai_story"):
                elements.append(Paragraph(entry.get("ai_story"), styles['Normal']))
            
            if entry.get("places_visited"):
                elements.append(Paragraph("Places Visited:", styles['Heading3']))
                for place in entry.get("places_visited"):
                    elements.append(Paragraph(f"- {place}", styles['Normal']))
                    
            if entry.get("notes"):
                elements.append(Paragraph("Notes:", styles['Heading3']))
                for note in entry.get("notes"):
                    elements.append(Paragraph(f"- {note}", styles['Normal']))
                    
            if entry.get("expenses"):
                elements.append(Paragraph("Expenses:", styles['Heading3']))
                data = [["Name", "Amount", "Currency"]]
                for exp in entry.get("expenses"):
                    data.append([exp.get("name"), str(exp.get("amount")), exp.get("currency")])
                table = Table(data)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ]))
                elements.append(table)
                
            elements.append(Spacer(1, 24))
            
        doc.build(elements)
        return buffer.getvalue()
