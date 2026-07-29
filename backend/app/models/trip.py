"""Firestore document shapes for the itinerary/trips feature."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

COLLECTION = "trips"


@dataclass
class DayPlan:
    day_number: int
    title: str
    activities: list[dict]  # [{time, title, description, location, estimated_cost}]


@dataclass
class Trip:
    id: str
    user_id: str
    destination: str
    start_date: str
    end_date: str
    budget: float
    currency: str
    travel_style: str
    days: list[dict]
    estimated_total_cost: float
    is_saved: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "destination": self.destination,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "budget": self.budget,
            "currency": self.currency,
            "travel_style": self.travel_style,
            "days": self.days,
            "estimated_total_cost": self.estimated_total_cost,
            "is_saved": self.is_saved,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_snapshot(doc_id: str, data: dict) -> "Trip":
        return Trip(
            id=doc_id,
            user_id=data["user_id"],
            destination=data["destination"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            budget=data["budget"],
            currency=data["currency"],
            travel_style=data["travel_style"],
            days=data["days"],
            estimated_total_cost=data["estimated_total_cost"],
            is_saved=data.get("is_saved", False),
            created_at=data.get("created_at", datetime.now(timezone.utc)),
        )
