from __future__ import annotations

import uuid
from datetime import datetime, timezone
from google.cloud.firestore import AsyncClient, Query
from fastapi import HTTPException

class DiaryRepository:
    def __init__(self, db: AsyncClient):
        self._db = db
    
    async def _verify_trip_ownership(self, trip_id: str, user_id: str) -> None:
        trip_doc = await self._db.collection("trips").document(trip_id).get()
        if not trip_doc.exists:
            raise HTTPException(status_code=404, detail="Trip not found")
        if trip_doc.to_dict().get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this trip")
            
    async def get_entries(self, trip_id: str, user_id: str) -> list[dict]:
        """Get all diary entries for a trip, ordered by date."""
        await self._verify_trip_ownership(trip_id, user_id)
        
        query = (
            self._db.collection("trips").document(trip_id).collection("diary_entries")
            .where("user_id", "==", user_id)
            .order_by("date", direction=Query.ASCENDING)
        )
        
        entries = []
        async for doc in query.stream():
            entries.append(doc.to_dict())
        return entries
    
    async def get_entry(self, trip_id: str, entry_id: str, user_id: str) -> dict | None:
        """Get a specific diary entry."""
        await self._verify_trip_ownership(trip_id, user_id)
        
        doc = await self._db.collection("trips").document(trip_id).collection("diary_entries").document(entry_id).get()
        if not doc.exists:
            return None
            
        data = doc.to_dict()
        if data.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
            
        return data
    
    async def create_or_update_entry(
        self,
        trip_id: str,
        user_id: str,
        date: str,
        data: dict,
    ) -> dict:
        """Create or update entry for a specific date. Returns full entry."""
        await self._verify_trip_ownership(trip_id, user_id)
        
        collection = self._db.collection("trips").document(trip_id).collection("diary_entries")
        
        # Check if entry for date already exists
        query = collection.where("user_id", "==", user_id).where("date", "==", date).limit(1)
        existing = [doc async for doc in query.stream()]
        
        now = datetime.now(timezone.utc)
        
        if existing:
            doc = existing[0]
            entry_id = doc.id
            entry_data = doc.to_dict()
            entry_data.update(data)
            entry_data["updated_at"] = now
        else:
            entry_id = str(uuid.uuid4())
            entry_data = {
                "id": entry_id,
                "trip_id": trip_id,
                "user_id": user_id,
                "date": date,
                "places_visited": [],
                "notes": [],
                "photos": [],
                "expenses": [],
                "ratings": {},
                "ai_story": None,
                "writing_style": "journal",
                "created_at": now,
                "updated_at": now,
            }
            entry_data.update(data)
            
        await collection.document(entry_id).set(entry_data)
        return entry_data
    
    async def update_entry(self, trip_id: str, entry_id: str, user_id: str, updates: dict) -> dict:
        """Update specific fields of an entry."""
        entry = await self.get_entry(trip_id, entry_id, user_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
            
        updates["updated_at"] = datetime.now(timezone.utc)
        
        # Merge dicts
        for k, v in updates.items():
            entry[k] = v
            
        await self._db.collection("trips").document(trip_id).collection("diary_entries").document(entry_id).set(entry)
        return entry
    
    async def delete_entry(self, trip_id: str, entry_id: str, user_id: str) -> None:
        """Delete a diary entry."""
        entry = await self.get_entry(trip_id, entry_id, user_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
            
        await self._db.collection("trips").document(trip_id).collection("diary_entries").document(entry_id).delete()
    
    async def get_trip_story(self, trip_id: str, user_id: str) -> dict | None:
        """Get the trip-level story document from trips/{trip_id}/trip_story/main."""
        await self._verify_trip_ownership(trip_id, user_id)
        
        doc = await self._db.collection("trips").document(trip_id).collection("trip_story").document("main").get()
        if not doc.exists:
            return None
            
        data = doc.to_dict()
        if data.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
            
        return data
    
    async def save_trip_story(self, trip_id: str, user_id: str, story: dict) -> dict:
        """Save/update the trip story."""
        await self._verify_trip_ownership(trip_id, user_id)
        
        story["user_id"] = user_id
        story["trip_id"] = trip_id
        story["updated_at"] = datetime.now(timezone.utc)
        
        await self._db.collection("trips").document(trip_id).collection("trip_story").document("main").set(story)
        return story
