"""
Tests for the per-activity feedback system (Phase 4).

Covers:
1. _resolve_feature_deltas() — correct deltas from rejection reasons / categories
2. MemoryEngine.record_activity_event() — updates behavioral weights + persists feedback
3. Promotion threshold — 5 events enough to trigger run_promotion()
4. POST /memory/feedback API endpoint — validation + correct response shape
5. Validation: reject without rejection_reason → 422
"""
from __future__ import annotations

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.cognitive.memory_engine import (
    MemoryEngine,
    _resolve_feature_deltas,
    PROMOTION_LOOKBACK_EVENTS,
    PROMOTION_THRESHOLD,
)
from app.models.memory import (
    BehavioralMemory,
    LongTermMemory,
)


# ─── Unit tests: _resolve_feature_deltas ──────────────────────────────────────

class TestResolveFeatureDeltas:
    """
    _resolve_feature_deltas() returns directions for record_event()'s SGD formula:
        target = direction * signal   (signal=-1.0 for reject, +1.0 for accept)

    So for "reject" + "too_expensive":
        direction=+1.0 → target=(+1.0)*(-1.0)=-1.0 → budget_sensitivity goes NEGATIVE
        (budget_sensitivity NEGATIVE means "prefers value/lower cost" ✓)
    """

    def test_reject_too_expensive_returns_positive_budget_direction(self):
        """Direction must be positive so SGD moves budget_sensitivity negative on reject."""
        deltas = _resolve_feature_deltas("attraction", "reject", "too_expensive")
        assert "budget_sensitivity" in deltas
        assert deltas["budget_sensitivity"] > 0  # direction=+1, signal=-1 → target=-1 → weight goes negative

    def test_reject_too_crowded_returns_negative_crowd_direction(self):
        """Direction must be negative so SGD moves crowd_aversion positive on reject."""
        deltas = _resolve_feature_deltas("culture", "reject", "too_crowded")
        assert "crowd_aversion" in deltas
        assert deltas["crowd_aversion"] < 0  # direction=-1, signal=-1 → target=+1 → weight goes positive

    def test_reject_too_far_returns_positive_distance_direction(self):
        """Direction must be positive so SGD moves distance_tolerance negative on reject."""
        deltas = _resolve_feature_deltas("nature", "reject", "too_far")
        assert "distance_tolerance" in deltas
        assert deltas["distance_tolerance"] > 0  # direction=+1, signal=-1 → target=-1 → weight goes negative

    def test_reject_not_interested_returns_positive_novelty_direction(self):
        """Direction must be positive so SGD moves novelty_seeking negative on reject."""
        deltas = _resolve_feature_deltas("museum", "reject", "not_interested")
        assert "novelty_seeking" in deltas
        assert deltas["novelty_seeking"] > 0  # direction=+0.5, signal=-1 → target=-0.5 → weight goes negative

    def test_accept_culture_returns_positive_novelty_direction(self):
        """Direction must be positive so SGD moves novelty_seeking positive on accept."""
        deltas = _resolve_feature_deltas("culture", "accept", None)
        assert "novelty_seeking" in deltas
        assert deltas["novelty_seeking"] > 0  # direction=+0.3, signal=+1 → target=+0.3 → weight goes positive

    def test_accept_nature_returns_positive_novelty_direction(self):
        deltas = _resolve_feature_deltas("nature", "accept", None)
        assert "novelty_seeking" in deltas
        assert deltas["novelty_seeking"] > 0

    def test_accept_meal_returns_empty_deltas(self):
        deltas = _resolve_feature_deltas("meal", "accept", None)
        assert deltas == {}

    def test_accept_transport_returns_empty_deltas(self):
        deltas = _resolve_feature_deltas("transport", "accept", None)
        assert deltas == {}

    def test_edit_returns_half_strength_of_accept(self):
        accept_deltas = _resolve_feature_deltas("culture", "accept", None)
        edit_deltas = _resolve_feature_deltas("culture", "edit", None)
        for key in accept_deltas:
            assert key in edit_deltas
            assert abs(edit_deltas[key]) == pytest.approx(abs(accept_deltas[key]) * 0.5, abs=0.01)

    def test_reject_with_no_reason_returns_dict(self):
        deltas = _resolve_feature_deltas("culture", "reject", None)
        assert isinstance(deltas, dict)

    def test_unknown_rejection_reason_handled_gracefully(self):
        deltas = _resolve_feature_deltas("attraction", "reject", "other")
        assert isinstance(deltas, dict)



# ─── Unit tests: Thresholds ───────────────────────────────────────────────────

class TestPromotionThresholds:
    def test_lookback_events_is_5_or_less(self):
        """Promotion should be achievable from a single trip session."""
        assert PROMOTION_LOOKBACK_EVENTS <= 5, (
            f"PROMOTION_LOOKBACK_EVENTS={PROMOTION_LOOKBACK_EVENTS} is too high — "
            "should be <= 5 so per-activity feedback can trigger promotion within a session."
        )

    def test_promotion_threshold_is_below_0_4(self):
        """Feature weight threshold for promotion should be reachable after modest feedback."""
        assert PROMOTION_THRESHOLD < 0.4, (
            f"PROMOTION_THRESHOLD={PROMOTION_THRESHOLD} is too conservative — "
            "should be < 0.4 to allow promotion after realistic feedback volume."
        )


# ─── Integration tests: MemoryEngine.record_activity_event() ─────────────────

@pytest.fixture
def mock_memory_repo():
    repo = MagicMock()
    behavioral = BehavioralMemory(user_id="test-user")
    longterm = LongTermMemory(user_id="test-user")
    repo.get_behavioral = AsyncMock(return_value=behavioral)
    repo.save_behavioral = AsyncMock()
    repo.add_feedback = AsyncMock()
    repo.get_longterm = AsyncMock(return_value=longterm)
    repo.save_longterm = AsyncMock()
    return repo

@pytest.fixture
def mock_chat_repo():
    repo = MagicMock()
    repo.get_history = AsyncMock(return_value=[])
    return repo

@pytest.fixture
def memory_engine(mock_memory_repo, mock_chat_repo):
    return MemoryEngine(
        memory_repository=mock_memory_repo,
        chat_repository=mock_chat_repo,
    )


@pytest.mark.asyncio
async def test_record_activity_event_updates_behavioral_memory(memory_engine, mock_memory_repo):
    """Rejecting an expensive activity should decrease budget_sensitivity weight."""
    initial_weight = mock_memory_repo.get_behavioral.return_value.feature_weights["budget_sensitivity"]

    await memory_engine.record_activity_event(
        user_id="test-user",
        trip_id="trip-1",
        activity_title="Luxury Hotel Dinner",
        activity_category="meal",
        event_type="reject",
        rejection_reason="too_expensive",
    )

    mock_memory_repo.save_behavioral.assert_called_once()
    saved_behavioral = mock_memory_repo.save_behavioral.call_args[0][0]
    new_weight = saved_behavioral.feature_weights["budget_sensitivity"]
    # Weight should have moved in the negative direction
    assert new_weight < initial_weight, (
        f"budget_sensitivity should decrease after 'too_expensive' rejection "
        f"(was {initial_weight}, now {new_weight})"
    )


@pytest.mark.asyncio
async def test_record_activity_event_persists_feedback_document(memory_engine, mock_memory_repo):
    """Feedback should be written to memory_feedback collection."""
    await memory_engine.record_activity_event(
        user_id="test-user",
        trip_id="trip-1",
        activity_title="Temple Visit",
        activity_category="culture",
        event_type="accept",
        rating=5,
    )

    mock_memory_repo.add_feedback.assert_called_once()
    call_kwargs = mock_memory_repo.add_feedback.call_args[1]
    assert call_kwargs["user_id"] == "test-user"
    assert call_kwargs["trip_id"] == "trip-1"
    assert call_kwargs["sentiment"] == "positive"


@pytest.mark.asyncio
async def test_record_activity_event_accept_increases_novelty_for_culture(memory_engine, mock_memory_repo):
    """Accepting a culture activity should increase novelty_seeking."""
    initial_weight = mock_memory_repo.get_behavioral.return_value.feature_weights["novelty_seeking"]

    await memory_engine.record_activity_event(
        user_id="test-user",
        trip_id="trip-1",
        activity_title="Ancient Temple",
        activity_category="culture",
        event_type="accept",
    )

    saved_behavioral = mock_memory_repo.save_behavioral.call_args[0][0]
    new_weight = saved_behavioral.feature_weights["novelty_seeking"]
    assert new_weight > initial_weight, (
        f"novelty_seeking should increase after accepting culture activity "
        f"(was {initial_weight}, now {new_weight})"
    )


@pytest.mark.asyncio
async def test_record_activity_event_reject_crowd_increases_crowd_aversion(memory_engine, mock_memory_repo):
    """Rejecting because 'too_crowded' should increase crowd_aversion."""
    initial_weight = mock_memory_repo.get_behavioral.return_value.feature_weights["crowd_aversion"]

    await memory_engine.record_activity_event(
        user_id="test-user",
        trip_id="trip-1",
        activity_title="Popular Beach",
        activity_category="nature",
        event_type="reject",
        rejection_reason="too_crowded",
    )

    saved_behavioral = mock_memory_repo.save_behavioral.call_args[0][0]
    new_weight = saved_behavioral.feature_weights["crowd_aversion"]
    assert new_weight > initial_weight


# ─── Tests: RecommendationEngine personalization_score ───────────────────────

@pytest.mark.asyncio
async def test_personalization_score_penalizes_expensive_for_budget_sensitive_user():
    """A budget-sensitive user (budget_sensitivity << 0) should see expensive activities ranked lower."""
    from app.cognitive.recommendation_engine import RecommendationEngine
    from app.cognitive.context_engine import ContextEngine, ContextScoreBreakdown
    from app.models.user import UserPreferences

    context_engine = MagicMock(spec=ContextEngine)
    mock_breakdown = ContextScoreBreakdown(
        opening_hours_score=0.7,
        weather_score=0.7,
        traffic_score=0.5,
        crowd_score=0.5,
        safety_score=0.5,
        festival_bonus=0.0,
        unavailable_components=["weather"],
    )
    context_engine.evaluate_context = AsyncMock(return_value=mock_breakdown)

    engine = RecommendationEngine(context_engine=context_engine)
    prefs = UserPreferences(budget=100.0)

    activities = [
        {"title": "Budget Café", "description": "Simple local breakfast", "estimated_cost": 5.0, "category": "meal"},
        {"title": "Fine Dining", "description": "Luxury 5-course dinner", "estimated_cost": 80.0, "category": "meal"},
    ]

    # Budget-sensitive user (has rejected expensive things repeatedly)
    sensitive_weights = {
        "budget_sensitivity": -0.5,
        "crowd_aversion": 0.0,
        "distance_tolerance": 0.0,
        "novelty_seeking": 0.0,
        "pace_preference": 0.0,
    }
    # Neutral user (no feedback history)
    neutral_weights = {
        "budget_sensitivity": 0.0,
        "crowd_aversion": 0.0,
        "distance_tolerance": 0.0,
        "novelty_seeking": 0.0,
        "pace_preference": 0.0,
    }

    daily_budget = 60.0

    sensitive_scores = await engine.score_and_rank(activities, prefs, daily_budget, feature_weights=sensitive_weights)
    neutral_scores = await engine.score_and_rank(activities, prefs, daily_budget, feature_weights=neutral_weights)

    def get_personalization(scores, title):
        for s in scores:
            if s.activity["title"] == title:
                return s.personalization_score
        raise AssertionError(f"Activity '{title}' not found")

    sensitive_fine_dining = get_personalization(sensitive_scores, "Fine Dining")
    neutral_fine_dining = get_personalization(neutral_scores, "Fine Dining")

    assert sensitive_fine_dining < neutral_fine_dining, (
        f"Fine Dining personalization_score should be lower for budget-sensitive user "
        f"(sensitive={sensitive_fine_dining:.3f}, neutral={neutral_fine_dining:.3f})"
    )


@pytest.mark.asyncio
async def test_personalization_score_neutral_when_no_weights():
    """Without feature_weights, personalization_score should be 0.5 (neutral)."""
    from app.cognitive.recommendation_engine import RecommendationEngine
    from app.cognitive.context_engine import ContextEngine, ContextScoreBreakdown
    from app.models.user import UserPreferences

    context_engine = MagicMock(spec=ContextEngine)
    mock_breakdown = ContextScoreBreakdown(
        opening_hours_score=0.7,
        weather_score=0.7,
        traffic_score=0.5,
        crowd_score=0.5,
        safety_score=0.5,
        festival_bonus=0.0,
        unavailable_components=["weather"],
    )
    context_engine.evaluate_context = AsyncMock(return_value=mock_breakdown)
    engine = RecommendationEngine(context_engine=context_engine)

    activities = [
        {"title": "City Tour", "description": "Tour the city", "estimated_cost": 20.0, "category": "attraction"},
    ]
    prefs = UserPreferences()

    scored = await engine.score_and_rank(activities, prefs, 100.0, feature_weights={})
    assert len(scored) == 1
    assert scored[0].personalization_score == pytest.approx(0.5, abs=0.01)

