from __future__ import annotations

import uuid

from google.cloud.firestore import AsyncClient, AsyncCollectionReference, Query

from app.models.trip import COLLECTION, Trip


class TripRepository:
    def __init__(self, db: AsyncClient) -> None:
        self._collection: AsyncCollectionReference = db.collection(COLLECTION)

    async def create(self, trip_data: dict) -> Trip:
        trip = Trip(id=str(uuid.uuid4()), **trip_data)
        await self._collection.document(trip.id).set(trip.to_dict())
        return trip

    async def get_by_id(self, trip_id: str) -> Trip | None:
        snapshot = await self._collection.document(trip_id).get()
        if not snapshot.exists:
            return None
        return Trip.from_snapshot(snapshot.id, snapshot.to_dict())

    async def list_for_user(self, user_id: str, *, saved_only: bool = False) -> list[Trip]:
        query = self._collection.where("user_id", "==", user_id)
        if saved_only:
            query = query.where("is_saved", "==", True)
        query = query.order_by("created_at", direction=Query.DESCENDING)

        trips: list[Trip] = []
        async for snapshot in query.stream():
            trips.append(Trip.from_snapshot(snapshot.id, snapshot.to_dict()))
        return trips

    async def set_saved(self, trip_id: str, is_saved: bool) -> None:
        await self._collection.document(trip_id).update({"is_saved": is_saved})

    async def delete(self, trip_id: str) -> None:
        await self._collection.document(trip_id).delete()
