"""User Profile Engine (SCIF Section 6, Phase 4 design Section 2.1)."""
from __future__ import annotations

from app.models.user import UserPreferences
from app.repositories.user_repository import UserRepository


class UserProfileEngine:
    def __init__(self, user_repository: UserRepository) -> None:
        self._users = user_repository

    async def get_preferences(self, user_id: str) -> UserPreferences:
        """
        Returns only the user's DECLARED preferences - never merged with
        inferred ones from memory. Keeping "what the user said" separate
        from "what we inferred" at every layer is what lets the
        Explainability Engine cite which kind of signal drove a
        recommendation, rather than blurring the two together.
        """
        user = await self._users.get_by_id(user_id)
        return user.preferences if user else UserPreferences()
