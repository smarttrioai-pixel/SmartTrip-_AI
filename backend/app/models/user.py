"""
User profile document for Firestore.

Document id == Firebase Authentication uid. Firebase owns the identity
(password, Google linkage, email verification flag) — this collection only
stores the app-specific profile that layers on top of it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

COLLECTION = "users"


@dataclass
class UserPreferences:
    budget: float | None = None
    currency: str = "USD"
    language: str = "en"
    travel_style: str = "balanced"  # relaxed | adventure | luxury | budget | balanced
    food_preference: str = "no_preference"
    accommodation: str = "hotel"  # hotel | hostel | resort | homestay
    transport: str = "any"  # flight | train | car | any
    accessibility_needs: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "budget": self.budget,
            "currency": self.currency,
            "language": self.language,
            "travel_style": self.travel_style,
            "food_preference": self.food_preference,
            "accommodation": self.accommodation,
            "transport": self.transport,
            "accessibility_needs": self.accessibility_needs,
            "interests": self.interests,
        }

    @staticmethod
    def from_dict(data: dict | None) -> "UserPreferences":
        data = data or {}
        return UserPreferences(
            budget=data.get("budget"),
            currency=data.get("currency", "USD"),
            language=data.get("language", "en"),
            travel_style=data.get("travel_style", "balanced"),
            food_preference=data.get("food_preference", "no_preference"),
            accommodation=data.get("accommodation", "hotel"),
            transport=data.get("transport", "any"),
            accessibility_needs=data.get("accessibility_needs", []),
            interests=data.get("interests", []),
        )


@dataclass
class User:
    id: str  # Firebase uid
    email: str
    full_name: str
    is_email_verified: bool = False
    is_active: bool = True
    preferences: UserPreferences = field(default_factory=UserPreferences)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """Shape written to Firestore. `id` is excluded — it's the doc id."""
        return {
            "email": self.email,
            "full_name": self.full_name,
            "is_email_verified": self.is_email_verified,
            "is_active": self.is_active,
            "preferences": self.preferences.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_snapshot(doc_id: str, data: dict) -> "User":
        return User(
            id=doc_id,
            email=data["email"],
            full_name=data["full_name"],
            is_email_verified=data.get("is_email_verified", False),
            is_active=data.get("is_active", True),
            preferences=UserPreferences.from_dict(data.get("preferences")),
            created_at=data.get("created_at", datetime.now(timezone.utc)),
            updated_at=data.get("updated_at", datetime.now(timezone.utc)),
        )
