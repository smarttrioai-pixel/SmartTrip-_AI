"""
Memory Engine (SCIF Section 6 / Phase 3 design doc Section 7).

This is the stable interface later phases (Cognitive Engines, Multi-Agent
Layer) will call through - `get_context()` is the one method Phase 4's
Recommendation Engine needs for pipeline stage 2 (Memory Retrieval).

Promotion note: the design doc specifies promotion should trigger "after
every trip completion." There's no trip-completion event in the system yet
(trips don't have an end-date-passed lifecycle hook - that's Phase 10
territory). For Phase 3, `run_promotion` is exposed as a method any caller
can invoke (wired to trip-save in trip_service.py for now, as a reasonable
proxy signal) rather than a background job - revisit once a real
completion event exists.
"""
from __future__ import annotations

from app.integrations.embeddings import cosine_similarity, embed_text
from app.models.memory import BehavioralEvent, InferredPreference, PreferenceEmbedding, new_id
from app.repositories.chat_repository import ChatRepository
from app.repositories.memory_repository import MemoryRepository

LEARNING_RATE = 0.1
TOP_K_PREFERENCES = 10
SIMILARITY_THRESHOLD = 0.6
PROMOTION_THRESHOLD = 0.4
PROMOTION_LOOKBACK_EVENTS = 25  # approx. last ~5 trips' worth of events

# Templated statements for the promotion algorithm (Phase 3 design doc,
# Section 5) - intentionally NOT freely LLM-generated, so every inferred
# preference is traceable to the exact feature/threshold that produced it,
# consistent with the Explainability Engine's grounding principle.
PROMOTION_TEMPLATES = {
    ("distance_tolerance", "low"): "You tend to prefer activities close to your accommodation.",
    ("distance_tolerance", "high"): "You're comfortable traveling further for the right activity.",
    ("budget_sensitivity", "low"): "You tend to prioritize value and lower-cost options.",
    ("budget_sensitivity", "high"): "You're comfortable spending more for higher-quality experiences.",
    ("crowd_aversion", "low"): "You don't mind crowded, popular attractions.",
    ("crowd_aversion", "high"): "You tend to prefer quieter, less crowded destinations.",
    ("novelty_seeking", "low"): "You tend to gravitate toward familiar, well-known experiences.",
    ("novelty_seeking", "high"): "You tend to seek out novel, off-the-beaten-path experiences.",
    ("pace_preference", "low"): "You prefer a relaxed, unhurried itinerary pace.",
    ("pace_preference", "high"): "You prefer a packed, activity-dense itinerary.",
}


class MemoryContext:
    """Combined output of get_context() - Phase 4 consumes this as-is."""

    def __init__(
        self,
        *,
        recent_conversation: list[dict],
        relevant_preferences: list[PreferenceEmbedding],
        feature_weights: dict,
    ) -> None:
        self.recent_conversation = recent_conversation
        self.relevant_preferences = relevant_preferences
        self.feature_weights = feature_weights

    def as_prompt_context(self) -> str:
        """Renders the memory context as text a planning prompt can include."""
        lines: list[str] = []
        if self.relevant_preferences:
            lines.append("Known user preferences, from past behavior:")
            for pref in self.relevant_preferences:
                lines.append(f"- {pref.source_text}")
        weight_notes = [f"{k}={v:+.2f}" for k, v in self.feature_weights.items() if abs(v) > 0.1]
        if weight_notes:
            lines.append("Learned tendencies: " + ", ".join(weight_notes))
        return "\n".join(lines)


class MemoryEngine:
    def __init__(self, memory_repository: MemoryRepository, chat_repository: ChatRepository) -> None:
        self._memory = memory_repository
        self._chats = chat_repository

    async def get_context(self, user_id: str, current_request_text: str, *, chat_id: str | None = None) -> MemoryContext:
        longterm = await self._memory.get_longterm(user_id)
        behavioral = await self._memory.get_behavioral(user_id)

        relevant_preferences: list[PreferenceEmbedding] = []
        if longterm.embeddings:
            query_vector = await embed_text(current_request_text)
            scored = [
                (cosine_similarity(query_vector, e.vector) * e.weight, e)
                for e in longterm.embeddings
            ]
            scored.sort(key=lambda pair: pair[0], reverse=True)
            relevant_preferences = [e for score, e in scored[:TOP_K_PREFERENCES] if score >= SIMILARITY_THRESHOLD]

        recent_conversation: list[dict] = []
        if chat_id:
            history = await self._chats.get_history(chat_id, limit=30)
            recent_conversation = [{"role": m.role, "content": m.content} for m in history]

        return MemoryContext(
            recent_conversation=recent_conversation,
            relevant_preferences=relevant_preferences,
            feature_weights=behavioral.feature_weights,
        )

    async def record_event(
        self, user_id: str, recommendation_id: str, event_type: str, feature_deltas: dict[str, float]
    ) -> None:
        behavioral = await self._memory.get_behavioral(user_id)

        signal = {"accept": 1.0, "reject": -1.0, "edit": 0.3}.get(event_type, 0.0)
        for feature, direction in feature_deltas.items():
            if feature not in behavioral.feature_weights:
                continue
            old_weight = behavioral.feature_weights[feature]
            target = max(-1.0, min(1.0, direction * signal))
            behavioral.feature_weights[feature] = old_weight + LEARNING_RATE * (target - old_weight)

        behavioral.recent_events.append(
            BehavioralEvent(recommendation_id=recommendation_id, event_type=event_type, feature_deltas=feature_deltas)
        )
        await self._memory.save_behavioral(behavioral)

    async def save_preference(self, user_id: str, source_text: str, source_type: str) -> None:
        vector = await embed_text(source_text)
        longterm = await self._memory.get_longterm(user_id)
        longterm.embeddings.append(
            PreferenceEmbedding(id=new_id(), vector=vector, source_text=source_text, source_type=source_type)
        )
        await self._memory.save_longterm(longterm)

    async def run_promotion(self, user_id: str) -> list[InferredPreference]:
        behavioral = await self._memory.get_behavioral(user_id)
        recent = behavioral.recent_events[-PROMOTION_LOOKBACK_EVENTS:]
        if len(recent) < PROMOTION_LOOKBACK_EVENTS:
            return []  # not enough signal yet to promote anything

        promoted: list[InferredPreference] = []
        longterm = await self._memory.get_longterm(user_id)
        already_promoted_features = {
            p.statement for p in longterm.inferred_preferences if p.status == "active"
        }

        for feature, weight in behavioral.feature_weights.items():
            if abs(weight) < PROMOTION_THRESHOLD:
                continue
            direction = "high" if weight > 0 else "low"
            statement = PROMOTION_TEMPLATES.get((feature, direction))
            if not statement or statement in already_promoted_features:
                continue

            supporting_events = sum(1 for e in recent if feature in e.feature_deltas)
            confidence = min(1.0, abs(weight) * (supporting_events / len(recent)))

            inference = InferredPreference(
                id=new_id(),
                statement=statement,
                confidence=round(confidence, 2),
                supporting_event_count=supporting_events,
            )
            longterm.inferred_preferences.append(inference)
            promoted.append(inference)

        if promoted:
            await self._memory.save_longterm(longterm)
        return promoted

    async def get_insights(self, user_id: str) -> dict:
        longterm = await self._memory.get_longterm(user_id)
        behavioral = await self._memory.get_behavioral(user_id)
        return {
            "preferences": longterm.embeddings,
            "inferred_preferences": [p for p in longterm.inferred_preferences if p.status == "active"],
            "feature_weights": behavioral.feature_weights,
        }

    async def reject_inference(self, user_id: str, inference_id: str) -> None:
        longterm = await self._memory.get_longterm(user_id)
        for pref in longterm.inferred_preferences:
            if pref.id == inference_id:
                pref.status = "user_rejected"
        await self._memory.save_longterm(longterm)
