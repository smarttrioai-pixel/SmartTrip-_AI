"""
Firestore-backed repository for the User profile.

Document id is always the Firebase Authentication uid — there is no
separate id generation here, unlike a typical repository, because identity
is owned by Firebase, not this collection.
"""
from __future__ import annotations

from datetime import datetime, timezone

from google.cloud.firestore import AsyncClient, AsyncCollectionReference

from app.models.user import COLLECTION, User


class UserRepository:
    def __init__(self, db: AsyncClient) -> None:
        self._collection: AsyncCollectionReference = db.collection(COLLECTION)

    async def get_by_id(self, user_id: str) -> User | None:
        snapshot = await self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return User.from_snapshot(snapshot.id, snapshot.to_dict())

    async def create(
        self,
        *,
        uid: str,
        email: str,
        full_name: str,
        is_email_verified: bool = False,
    ) -> User:
        user = User(id=uid, email=email, full_name=full_name, is_email_verified=is_email_verified)
        await self._collection.document(uid).set(user.to_dict())
        return user

    async def update_preferences(self, user_id: str, preferences: dict) -> User:
        await self._collection.document(user_id).update(
            {"preferences": preferences, "updated_at": datetime.now(timezone.utc)}
        )
        return await self.get_by_id(user_id)  # type: ignore[return-value]

    async def update_profile(self, user_id: str, *, full_name: str) -> User:
        await self._collection.document(user_id).update(
            {"full_name": full_name, "updated_at": datetime.now(timezone.utc)}
        )
        return await self.get_by_id(user_id)  # type: ignore[return-value]
