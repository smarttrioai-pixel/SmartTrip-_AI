"""
Firestore document shapes for the Memory Layer (Phase 3).

Long-term and Behavioral memory are one document per user (doc id = uid) -
per-user embedding/event counts are small enough that a single document
read retrieves everything needed for a planning request, with no fan-out
query. Feedback memory is append-only, auto-id, queried by user_id.

Short-term (session) memory is deliberately NOT modeled here - it reuses
the existing chats/{id}/messages subcollection rather than duplicating
storage (see Phase 3 design doc, Section 2.1).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

LONGTERM_COLLECTION = "memory_longterm"
BEHAVIORAL_COLLECTION = "memory_behavioral"
FEEDBACK_COLLECTION = "memory_feedback"

DEFAULT_FEATURE_WEIGHTS = {
    "budget_sensitivity": 0.0,
    "crowd_aversion": 0.0,
    "distance_tolerance": 0.0,
    "novelty_seeking": 0.0,
    "pace_preference": 0.0,
}


@dataclass
class PreferenceEmbedding:
    id: str
    vector: list[float]
    source_text: str
    source_type: str
    weight: float = 1.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "vector": self.vector,
            "source_text": self.source_text,
            "source_type": self.source_type,
            "weight": self.weight,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(data: dict) -> "PreferenceEmbedding":
        return PreferenceEmbedding(
            id=data["id"],
            vector=data["vector"],
            source_text=data["source_text"],
            source_type=data["source_type"],
            weight=data.get("weight", 1.0),
            created_at=data.get("created_at", datetime.now(timezone.utc)),
        )


@dataclass
class InferredPreference:
    id: str
    statement: str
    confidence: float
    supporting_event_count: int
    promoted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "active"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "statement": self.statement,
            "confidence": self.confidence,
            "supporting_event_count": self.supporting_event_count,
            "promoted_at": self.promoted_at,
            "status": self.status,
        }

    @staticmethod
    def from_dict(data: dict) -> "InferredPreference":
        return InferredPreference(
            id=data["id"],
            statement=data["statement"],
            confidence=data["confidence"],
            supporting_event_count=data["supporting_event_count"],
            promoted_at=data.get("promoted_at", datetime.now(timezone.utc)),
            status=data.get("status", "active"),
        )


@dataclass
class LongTermMemory:
    user_id: str
    embeddings: list[PreferenceEmbedding] = field(default_factory=list)
    inferred_preferences: list[InferredPreference] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "embeddings": [e.to_dict() for e in self.embeddings],
            "inferred_preferences": [p.to_dict() for p in self.inferred_preferences],
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(user_id: str, data: dict | None) -> "LongTermMemory":
        data = data or {}
        return LongTermMemory(
            user_id=user_id,
            embeddings=[PreferenceEmbedding.from_dict(e) for e in data.get("embeddings", [])],
            inferred_preferences=[
                InferredPreference.from_dict(p) for p in data.get("inferred_preferences", [])
            ],
            updated_at=data.get("updated_at", datetime.now(timezone.utc)),
        )


@dataclass
class BehavioralEvent:
    recommendation_id: str
    event_type: str
    feature_deltas: dict
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "recommendation_id": self.recommendation_id,
            "event_type": self.event_type,
            "feature_deltas": self.feature_deltas,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_dict(data: dict) -> "BehavioralEvent":
        return BehavioralEvent(
            recommendation_id=data["recommendation_id"],
            event_type=data["event_type"],
            feature_deltas=data["feature_deltas"],
            timestamp=data.get("timestamp", datetime.now(timezone.utc)),
        )


RECENT_EVENTS_CAP = 200


@dataclass
class BehavioralMemory:
    user_id: str
    feature_weights: dict = field(default_factory=lambda: dict(DEFAULT_FEATURE_WEIGHTS))
    recent_events: list[BehavioralEvent] = field(default_factory=list)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "feature_weights": self.feature_weights,
            "recent_events": [e.to_dict() for e in self.recent_events[-RECENT_EVENTS_CAP:]],
            "last_updated": self.last_updated,
        }

    @staticmethod
    def from_dict(user_id: str, data: dict | None) -> "BehavioralMemory":
        data = data or {}
        weights = dict(DEFAULT_FEATURE_WEIGHTS)
        weights.update(data.get("feature_weights", {}))
        return BehavioralMemory(
            user_id=user_id,
            feature_weights=weights,
            recent_events=[BehavioralEvent.from_dict(e) for e in data.get("recent_events", [])],
            last_updated=data.get("last_updated", datetime.now(timezone.utc)),
        )


@dataclass
class FeedbackMemory:
    id: str
    user_id: str
    trip_id: str
    rating: int
    sentiment: str
    would_revisit: bool | None = None
    free_text: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "trip_id": self.trip_id,
            "rating": self.rating,
            "sentiment": self.sentiment,
            "would_revisit": self.would_revisit,
            "free_text": self.free_text,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_snapshot(doc_id: str, data: dict) -> "FeedbackMemory":
        return FeedbackMemory(
            id=doc_id,
            user_id=data["user_id"],
            trip_id=data["trip_id"],
            rating=data["rating"],
            sentiment=data["sentiment"],
            would_revisit=data.get("would_revisit"),
            free_text=data.get("free_text"),
            created_at=data.get("created_at", datetime.now(timezone.utc)),
        )


def new_id() -> str:
    return str(uuid.uuid4())
