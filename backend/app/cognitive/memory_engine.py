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
# Threshold for feature weight before a behavioral pattern qualifies for promotion
# to a named InferredPreference. Lowered from 0.4 to 0.3 to enable earlier promotion
# once genuine per-activity feedback (not just trip-save events) is collected.
PROMOTION_THRESHOLD = 0.3
# How many recent events are needed before promotion is evaluated.
# Lowered from 25 (which required ~25 trip saves) to 5 (achievable from
# per-activity feedback in a single trip session).
PROMOTION_LOOKBACK_EVENTS = 5  # approx. 1 trip's worth of per-activity feedback

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


# ---------------------------------------------------------------------------
# Feature-delta resolution helpers
# ---------------------------------------------------------------------------

# Maps (rejection_reason) → {feature: direction}
# IMPORTANT: These directions are fed into record_event() which uses:
#   target = direction * signal   where signal=-1.0 for "reject"
# So to make budget_sensitivity go NEGATIVE after "too_expensive":
#   direction=+1.0 → target=(+1.0)*(-1.0)=-1.0 → weight moves negative ✓
#
# Desired semantic:
#   too_expensive  → budget_sensitivity goes NEGATIVE  (low = "prefers value")
#   too_crowded    → crowd_aversion goes POSITIVE       (high = "avoids crowds")
#   too_far        → distance_tolerance goes NEGATIVE   (low = "prefers nearby")
#   not_interested → novelty_seeking goes NEGATIVE      (low = "less novelty")
#   already_visited→ novelty_seeking goes POSITIVE      (high = "seek new things")
_REJECTION_REASON_DELTAS: dict[str, dict[str, float]] = {
    "too_expensive":   {"budget_sensitivity": 1.0},    # reject: target = 1.0*(-1.0) = -1.0 ✓
    "too_crowded":     {"crowd_aversion": -1.0},        # reject: target = (-1.0)*(-1.0) = +1.0 ✓
    "too_far":         {"distance_tolerance": 1.0},     # reject: target = 1.0*(-1.0) = -1.0 ✓
    "not_interested":  {"novelty_seeking": 0.5},        # reject: target = 0.5*(-1.0) = -0.5 ✓
    "already_visited": {"novelty_seeking": -0.5},       # reject: target = (-0.5)*(-1.0) = +0.5 ✓
    "wrong_type":      {},
    "other":           {},
}

# Maps activity category → feature directions for ACCEPT event (signal=+1.0)
# To increase novelty_seeking: direction=+1.0 → target=(+1.0)*(+1.0)=+1.0 ✓
_CATEGORY_ACCEPT_DELTAS: dict[str, dict[str, float]] = {
    "culture":     {"novelty_seeking": 0.3},
    "attraction":  {"novelty_seeking": 0.2},
    "museum":      {"novelty_seeking": 0.3},
    "nature":      {"novelty_seeking": 0.4, "crowd_aversion": 0.2},
    "shopping":    {"novelty_seeking": -0.2},
    "meal":        {},
    "transport":   {},
    "other":       {},
}



def _resolve_feature_deltas(
    activity_category: str,
    event_type: str,
    rejection_reason: str | None,
) -> dict[str, float]:
    """
    Map an activity feedback event to behavioral feature deltas.

    Rules:
    - On reject: deltas primarily come from the rejection_reason (what the user
      disliked). Category gives a weaker secondary signal.
    - On accept: deltas come from the category (what kind of thing the user liked).
    - On edit:  mild deltas, half the strength of accept.

    Returns: dict[feature_name → direction] where direction is in [-1, +1].
    The actual update magnitude is controlled by LEARNING_RATE in record_event().
    """
    deltas: dict[str, float] = {}

    if event_type == "reject":
        # Primary signal: rejection reason
        if rejection_reason and rejection_reason in _REJECTION_REASON_DELTAS:
            deltas.update(_REJECTION_REASON_DELTAS[rejection_reason])
        # Secondary signal: category (mild — -0.1 interest bias)
        cat = (activity_category or "").lower()
        if cat in ("attraction", "culture", "museum", "nature"):
            # Rejected a cultural/nature activity: mild novelty-seeking reduction
            deltas.setdefault("novelty_seeking", -0.1)

    elif event_type == "accept":
        cat = (activity_category or "").lower()
        category_deltas = _CATEGORY_ACCEPT_DELTAS.get(cat, {})
        deltas.update(category_deltas)

    elif event_type == "edit":
        # Edit = mild positive signal (user liked it enough to keep, just changed it)
        cat = (activity_category or "").lower()
        category_deltas = _CATEGORY_ACCEPT_DELTAS.get(cat, {})
        # Half the strength of accept
        deltas.update({k: v * 0.5 for k, v in category_deltas.items()})

    return deltas


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

    async def record_activity_event(
        self,
        *,
        user_id: str,
        trip_id: str,
        activity_title: str,
        activity_category: str,
        event_type: str,          # "accept" | "reject" | "edit"
        rejection_reason: str | None = None,
        rating: int | None = None,
        free_text: str | None = None,
    ) -> None:
        """
        High-level method called by the /memory/feedback API endpoint.

        1. Resolves feature_deltas from activity category + rejection_reason.
        2. Calls record_event() to update behavioral feature_weights in Firestore.
        3. Persists a FeedbackMemory document to memory_feedback collection.
        4. Triggers run_promotion() to promote strong patterns to InferredPreferences.
        """
        feature_deltas = _resolve_feature_deltas(activity_category, event_type, rejection_reason)

        # 1. Update behavioral memory (feature weights)
        await self.record_event(user_id, trip_id, event_type, feature_deltas)

        # 2. Persist feedback document to memory_feedback collection
        #    Derive sentiment from event_type + rating
        if event_type == "accept":
            sentiment = "positive"
        elif event_type == "reject":
            sentiment = "negative"
        else:
            sentiment = "neutral"

        if rating is not None:
            if rating >= 4:
                sentiment = "positive"
            elif rating <= 2:
                sentiment = "negative"
            else:
                sentiment = "neutral"

        full_text = activity_title
        if rejection_reason:
            full_text += f" | reason: {rejection_reason}"
        if free_text:
            full_text += f" | note: {free_text}"

        await self._memory.add_feedback(
            user_id=user_id,
            trip_id=trip_id,
            rating=rating if rating is not None else (5 if event_type == "accept" else 1),
            sentiment=sentiment,
            would_revisit=(event_type == "accept"),
            free_text=full_text if full_text != activity_title else free_text,
        )

        # 3. Attempt to promote behavioral patterns to InferredPreferences
        try:
            await self.run_promotion(user_id)
        except Exception:
            pass  # promotion is non-critical; don't fail the feedback call



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
