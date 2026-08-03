"""
Run with: pytest tests/test_cognitive_engines.py

Updated for Phase 3B's consolidated RecommendationEngine/ContextEngine API.
The previous version of this file called ContextEngine.score_activity()
(a sync method) and RecommendationEngine.score_and_rank() without await —
neither matches this codebase's actual engines (score_activity never
existed here at all; score_and_rank is async). This file was already
broken/stale before Phase 3B, evidenced by score_activity not existing
anywhere in context_engine.py - not a regression introduced by this pass.
"""
import pytest

from app.cognitive.context_engine import ContextEngine
from app.cognitive.explainability_engine import ExplainabilityEngine
from app.cognitive.recommendation_engine import RecommendationEngine, ScoredActivity
from app.cognitive.risk_assessment_engine import RiskAssessmentEngine
from app.models.user import UserPreferences

pytestmark = pytest.mark.asyncio


async def test_context_engine_scores_daytime_activity_higher():
    engine = ContextEngine()
    daytime = await engine.evaluate_context({"time": "10:00 AM"})
    late_night = await engine.evaluate_context({"time": "3:00 AM"})
    assert daytime.opening_hours_score > late_night.opening_hours_score


async def test_context_engine_unknown_time_returns_documented_default():
    engine = ContextEngine()
    result = await engine.evaluate_context({"time": "sometime"})
    # _score_opening_hours returns 0.75 for unparseable time strings in
    # this codebase's implementation (not a generic 0.5 neutral value).
    assert result.opening_hours_score == 0.75


async def test_context_engine_flags_weather_unavailable_without_coordinates():
    engine = ContextEngine()
    result = await engine.evaluate_context({"time": "10:00 AM"}, lat=None, lon=None)
    # traffic/crowd/safety have no real data source at all yet regardless
    # of coordinates; weather is only unavailable when lat/lon are missing.
    assert set(result.unavailable_components) == {"weather", "traffic", "crowd", "safety"}


async def test_recommendation_engine_budget_fit_scoring():
    engine = RecommendationEngine(ContextEngine())
    cheap = {"time": "10:00 AM", "title": "Park visit", "description": "Walk in the park", "estimated_cost": 5}
    expensive = {"time": "11:00 AM", "title": "Fine dining", "description": "Tasting menu", "estimated_cost": 500}

    scored = await engine.score_and_rank([cheap, expensive], UserPreferences(), daily_budget_hint=50)

    by_title = {s.activity["title"]: s for s in scored}
    assert by_title["Park visit"].budget_match > by_title["Fine dining"].budget_match


async def test_recommendation_engine_interest_match_keyword_overlap():
    engine = RecommendationEngine(ContextEngine())
    museum = {"time": "10:00 AM", "title": "Art Museum", "description": "Modern art collection", "estimated_cost": 10}
    generic = {"time": "11:00 AM", "title": "City Walk", "description": "General stroll", "estimated_cost": 0}

    preferences = UserPreferences(interests=["art", "museums"])
    scored = await engine.score_and_rank([museum, generic], preferences, daily_budget_hint=50)

    by_title = {s.activity["title"]: s for s in scored}
    assert by_title["Art Museum"].interest_match > by_title["City Walk"].interest_match


async def test_recommendation_engine_no_interests_is_neutral_not_penalized():
    engine = RecommendationEngine(ContextEngine())
    activity = {"time": "10:00 AM", "title": "Anything", "description": "Some activity", "estimated_cost": 10}

    scored = await engine.score_and_rank([activity], UserPreferences(interests=[]), daily_budget_hint=50)

    assert scored[0].interest_match == 0.5


async def test_recommendation_engine_flags_distance_and_popularity_unavailable():
    engine = RecommendationEngine(ContextEngine())
    activity = {"time": "10:00 AM", "title": "Anything", "description": "Some activity", "estimated_cost": 10}

    scored = await engine.score_and_rank([activity], UserPreferences(), daily_budget_hint=50)

    assert "distance_match" in scored[0].unavailable_factors
    assert "popularity_score" in scored[0].unavailable_factors


async def test_explainability_engine_cites_high_interest_match():
    context = await ContextEngine().evaluate_context({"time": "10:00 AM"})
    scored = ScoredActivity(
        activity={"title": "Art Museum"},
        budget_match=0.9,
        interest_match=0.9,
        context=context,
        composite_score=0.9,
    )

    explanation = ExplainabilityEngine().explain(scored)

    assert "interests" in explanation.reason_text.lower()
    assert "budget" in explanation.reason_text.lower()
    assert 0 < explanation.confidence <= 1.0


async def test_explainability_engine_never_claims_unavailable_weather():
    # No coordinates -> weather is unavailable; explanation must not cite
    # "favorable weather" for a factor that was never actually checked.
    context = await ContextEngine().evaluate_context({"time": "10:00 AM"}, lat=None, lon=None)
    scored = ScoredActivity(
        activity={"title": "Anything"},
        budget_match=0.5,
        interest_match=0.5,
        context=context,
        composite_score=0.5,
    )

    explanation = ExplainabilityEngine().explain(scored)

    assert "weather" not in explanation.reason_text.lower()


def test_risk_assessment_engine_returns_low_score_for_benign_activity():
    engine = RiskAssessmentEngine()
    result = engine.score_trip([{"day_number": 1, "activities": []}])
    assert 0.0 <= result <= 0.1
