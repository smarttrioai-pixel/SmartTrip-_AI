"""
Firestore document shape for SCPM training records.

Collection path: scpm_training_records/{user_id}/records/{record_id}

Each document represents one labelled feedback event.
Features are stored pre-computed (as they existed at feedback time)
so that the training set is always reproducible without needing to
re-query the original activity data.

IMPORTANT: 'label' is the ground-truth target variable.
  label = 1  →  user accepted / liked the activity
  label = 0  →  user rejected / disliked the activity

'label' is NEVER used as a feature during training. It is only used as y.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class SCPMTrainingRecord:
    """One labelled example for SCPM training."""

    # Identity
    id: str = field(default_factory=_new_id)
    user_id: str = ""
    trip_id: str = ""
    activity_title: str = ""

    # Activity features (known BEFORE feedback)
    category: str = "other"
    estimated_cost: float = 0.0
    daily_budget_hint: float = 0.0

    # Context features (from ContextEngine at planning time)
    weather_score: float = 0.5
    opening_hrs_score: float = 0.75
    context_composite: float = 0.5

    # User behavioral features (from memory_behavioral/{uid} at planning time)
    budget_sensitivity: float = 0.0
    crowd_aversion: float = 0.0
    novelty_seeking: float = 0.0
    distance_tolerance: float = 0.0
    pace_preference: float = 0.0

    # Ground-truth label (from user feedback)
    # 1 = accept/like,  0 = reject/dislike
    # 'edit' events are not stored as training records (ambiguous label)
    label: int = 1

    # Audit trail
    event_type: str = "accept"   # "accept" | "reject"
    rejection_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "trip_id": self.trip_id,
            "activity_title": self.activity_title,
            "category": self.category,
            "estimated_cost": self.estimated_cost,
            "daily_budget_hint": self.daily_budget_hint,
            "weather_score": self.weather_score,
            "opening_hrs_score": self.opening_hrs_score,
            "context_composite": self.context_composite,
            "budget_sensitivity": self.budget_sensitivity,
            "crowd_aversion": self.crowd_aversion,
            "novelty_seeking": self.novelty_seeking,
            "distance_tolerance": self.distance_tolerance,
            "pace_preference": self.pace_preference,
            "label": self.label,
            "event_type": self.event_type,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(data: dict) -> "SCPMTrainingRecord":
        return SCPMTrainingRecord(
            id=data.get("id", _new_id()),
            user_id=data.get("user_id", ""),
            trip_id=data.get("trip_id", ""),
            activity_title=data.get("activity_title", ""),
            category=data.get("category", "other"),
            estimated_cost=float(data.get("estimated_cost", 0.0)),
            daily_budget_hint=float(data.get("daily_budget_hint", 0.0)),
            weather_score=float(data.get("weather_score", 0.5)),
            opening_hrs_score=float(data.get("opening_hrs_score", 0.75)),
            context_composite=float(data.get("context_composite", 0.5)),
            budget_sensitivity=float(data.get("budget_sensitivity", 0.0)),
            crowd_aversion=float(data.get("crowd_aversion", 0.0)),
            novelty_seeking=float(data.get("novelty_seeking", 0.0)),
            distance_tolerance=float(data.get("distance_tolerance", 0.0)),
            pace_preference=float(data.get("pace_preference", 0.0)),
            label=int(data.get("label", 1)),
            event_type=data.get("event_type", "accept"),
            rejection_reason=data.get("rejection_reason"),
            created_at=data.get("created_at", datetime.now(timezone.utc)),
        )
