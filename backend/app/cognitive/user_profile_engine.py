"""
User Profile Engine for SmartTrip AI (SCIF Framework).
Manages declared user preferences, travel history metadata, and profile settings
with caching, logging, and explicit dependency injection.
"""
from __future__ import annotations

import logging
from typing import Any

from app.models.user import UserPreferences, UserProfile
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

class UserProfileEngine:
    def __init__(self, user_repository: UserRepository) -> None:
        self._users = user_repository
        self._cache: dict[str, UserPreferences] = {}

    async def get_preferences(self, user_id: str) -> UserPreferences:
        """Fetch declared user preferences (cached for fast access)."""
        if user_id in self._cache:
            return self._cache[user_id]

        user = await self._users.get_by_id(user_id)
        prefs = user.preferences if user else UserPreferences()
        self._cache[user_id] = prefs
        return prefs

    async def update_preferences(self, user_id: str, updates: dict[str, Any]) -> UserPreferences:
        """Update user preferences and invalidate cache."""
        user = await self._users.get_by_id(user_id)
        if not user:
            user = UserProfile(id=user_id, email=f"{user_id}@smarttrip.ai", preferences=UserPreferences())

        current_prefs = user.preferences.dict()
        current_prefs.update(updates)
        updated_prefs = UserPreferences(**current_prefs)
        user.preferences = updated_prefs

        await self._users.save(user)
        self._cache[user_id] = updated_prefs
        logger.info("Updated declared preferences for user %s", user_id)
        return updated_prefs

    async def get_profile(self, user_id: str) -> UserProfile | None:
        """Fetch complete user profile model."""
        return await self._users.get_by_id(user_id)
