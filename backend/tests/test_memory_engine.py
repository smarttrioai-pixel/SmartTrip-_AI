"""
Run with: pytest tests/test_memory_engine.py

Uses in-memory fake repositories - no real Firestore or Gemini API needed.
get_context()'s embedding path is exercised only when longterm.embeddings is
non-empty; tests here keep it empty to avoid needing a Gemini mock, except
where explicitly testing similarity ranking (monkeypatched).
"""
import pytest

from app.cognitive.memory_engine import (
    PROMOTION_LOOKBACK_EVENTS,
    PROMOTION_THRESHOLD,
    MemoryEngine,
)
from app.models.memory import BehavioralMemory, DEFAULT_FEATURE_WEIGHTS, LongTermMemory

pytestmark = pytest.mark.asyncio


class FakeMemoryRepository:
    def __init__(self):
        self._longterm: dict[str, LongTermMemory] = {}
        self._behavioral: dict[str, BehavioralMemory] = {}

    async def get_longterm(self, user_id):
        return self._longterm.get(user_id) or LongTermMemory(user_id=user_id)

    async def save_longterm(self, memory):
        self._longterm[memory.user_id] = memory

    async def get_behavioral(self, user_id):
        return self._behavioral.get(user_id) or BehavioralMemory(
            user_id=user_id, feature_weights=dict(DEFAULT_FEATURE_WEIGHTS)
        )

    async def save_behavioral(self, memory):
        self._behavioral[memory.user_id] = memory


class FakeChatRepository:
    async def get_history(self, chat_id, *, limit=30):
        return []


@pytest.fixture
def engine():
    return MemoryEngine(FakeMemoryRepository(), FakeChatRepository())


async def test_get_context_with_no_memory_returns_defaults(engine):
    context = await engine.get_context("user-1", "plan a trip to Kyoto")

    assert context.relevant_preferences == []
    assert context.feature_weights == DEFAULT_FEATURE_WEIGHTS


async def test_record_event_accept_moves_weight_toward_target(engine):
    await engine.record_event("user-1", "rec-1", "accept", {"distance_tolerance": -1.0})

    behavioral = await engine._memory.get_behavioral("user-1")
    # signal=+1 for accept, direction=-1 -> target=-1, EMA nudges old_weight (0.0) toward -1
    assert behavioral.feature_weights["distance_tolerance"] < 0
    assert len(behavioral.recent_events) == 1


async def test_record_event_reject_moves_weight_opposite_direction(engine):
    await engine.record_event("user-1", "rec-1", "reject", {"crowd_aversion": 1.0})

    behavioral = await engine._memory.get_behavioral("user-1")
    # signal=-1 for reject, direction=+1 -> target=-1, weight moves negative
    assert behavioral.feature_weights["crowd_aversion"] < 0


async def test_run_promotion_returns_empty_without_enough_events(engine):
    for _ in range(PROMOTION_LOOKBACK_EVENTS - 1):
        await engine.record_event("user-1", "rec-x", "accept", {"distance_tolerance": -1.0})

    promoted = await engine.run_promotion("user-1")
    assert promoted == []


async def test_run_promotion_promotes_consistent_strong_signal(engine):
    for _ in range(PROMOTION_LOOKBACK_EVENTS):
        await engine.record_event("user-1", "rec-x", "accept", {"distance_tolerance": -1.0})

    behavioral = await engine._memory.get_behavioral("user-1")
    assert abs(behavioral.feature_weights["distance_tolerance"]) >= PROMOTION_THRESHOLD

    promoted = await engine.run_promotion("user-1")

    assert len(promoted) == 1
    assert "close to your accommodation" in promoted[0].statement
    assert 0 < promoted[0].confidence <= 1.0


async def test_run_promotion_does_not_duplicate_existing_inference(engine):
    for _ in range(PROMOTION_LOOKBACK_EVENTS):
        await engine.record_event("user-1", "rec-x", "accept", {"distance_tolerance": -1.0})

    first = await engine.run_promotion("user-1")
    assert len(first) == 1

    for _ in range(PROMOTION_LOOKBACK_EVENTS):
        await engine.record_event("user-1", "rec-y", "accept", {"distance_tolerance": -1.0})

    second = await engine.run_promotion("user-1")
    assert second == []  # already active, not re-promoted


async def test_reject_inference_marks_status(engine):
    for _ in range(PROMOTION_LOOKBACK_EVENTS):
        await engine.record_event("user-1", "rec-x", "accept", {"distance_tolerance": -1.0})
    promoted = await engine.run_promotion("user-1")
    inference_id = promoted[0].id

    await engine.reject_inference("user-1", inference_id)

    insights = await engine.get_insights("user-1")
    assert insights["inferred_preferences"] == []  # rejected ones are filtered from active insights
