from __future__ import annotations

from datetime import datetime, timezone

from google.cloud.firestore import AsyncClient, Query

from app.models.memory import (
    BEHAVIORAL_COLLECTION,
    FEEDBACK_COLLECTION,
    LONGTERM_COLLECTION,
    BehavioralMemory,
    FeedbackMemory,
    LongTermMemory,
    new_id,
)


class MemoryRepository:
    """
    Owns all Firestore access for the three persisted memory tiers.
    Short-term memory has no repository here - it's read directly from the
    existing ChatRepository by whoever assembles a MemoryContext.
    """

    def __init__(self, db: AsyncClient) -> None:
        self._longterm = db.collection(LONGTERM_COLLECTION)
        self._behavioral = db.collection(BEHAVIORAL_COLLECTION)
        self._feedback = db.collection(FEEDBACK_COLLECTION)

    # --- Long-term memory ---

    async def get_longterm(self, user_id: str) -> LongTermMemory:
        snapshot = await self._longterm.document(user_id).get()
        return LongTermMemory.from_dict(user_id, snapshot.to_dict() if snapshot.exists else None)

    async def save_longterm(self, memory: LongTermMemory) -> None:
        memory.updated_at = datetime.now(timezone.utc)
        await self._longterm.document(memory.user_id).set(memory.to_dict())

    # --- Behavioral memory ---

    async def get_behavioral(self, user_id: str) -> BehavioralMemory:
        snapshot = await self._behavioral.document(user_id).get()
        return BehavioralMemory.from_dict(user_id, snapshot.to_dict() if snapshot.exists else None)

    async def save_behavioral(self, memory: BehavioralMemory) -> None:
        memory.last_updated = datetime.now(timezone.utc)
        await self._behavioral.document(memory.user_id).set(memory.to_dict())

    # --- Feedback memory ---

    async def add_feedback(
        self,
        *,
        user_id: str,
        trip_id: str,
        rating: int,
        sentiment: str,
        would_revisit: bool | None = None,
        free_text: str | None = None,
    ) -> FeedbackMemory:
        feedback = FeedbackMemory(
            id=new_id(),
            user_id=user_id,
            trip_id=trip_id,
            rating=rating,
            sentiment=sentiment,
            would_revisit=would_revisit,
            free_text=free_text,
        )
        await self._feedback.document(feedback.id).set(feedback.to_dict())
        return feedback

    async def list_feedback_for_user(self, user_id: str, *, limit: int = 20) -> list[FeedbackMemory]:
        query = (
            self._feedback.where("user_id", "==", user_id)
            .order_by("created_at", direction=Query.DESCENDING)
            .limit(limit)
        )
        results: list[FeedbackMemory] = []
        async for snapshot in query.stream():
            results.append(FeedbackMemory.from_snapshot(snapshot.id, snapshot.to_dict()))
        return results
