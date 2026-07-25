"""
Run with: pytest tests/test_cognitive_engines.py

Tests each Phase 4 engine in isolation, no Firestore/Gemini needed except
where explicitly noted (none here - Planning Engine's Gemini call is
exercised at the integration level, not unit-tested with a live API).
"""
from app.cognitive.context_engine import ContextEngine
from app.cognitive.explainability_engine import ExplainabilityEngine
from app.cognitive.recommendation_engine import RecommendationEngine
from app.cognitive.risk_assessment_engine import RiskAssessmentEngine
from app.models.user import UserPreferences


def test_context_engine_scores_daytime_activity_higher():
    engine = ContextEngine()
    daytime = engine.score_activity({"time": "10:00 AM"})
    late_night = engine.score_activity({"time": "3:00 AM"})

    assert daytime.opening_hours_score > late_night.opening_hours_score


def test_context_engine_unknown_time_is_neutral():
    engine = ContextEngine()
    result = engine.score_activity({"time": "sometime"})
    assert result.opening_hours_score == 0.5


def test_context_engine_flags_unavailable_components():
    engine = ContextEngine()
    result = engine.score_activity({"time": "10:00 AM"})
    assert set(result.unavailable_components) == {"weather", "traffic", "crowd", "safety"}


def test_recommendation_engine_budget_fit_scoring():
    engine = RecommendationEngine(ContextEngine())
    cheap = {"time": "10:00 AM", "title": "Park visit", "description": "Walk in the park", "estimated_cost": 5}
    expensive = {"time": "11:00 AM", "title": "Fine dining", "description": "Tasting menu", "estimated_cost": 500}

    scored = engine.score_and_rank([cheap, expensive], UserPreferences(), daily_budget_hint=50)

    by_title = {s.activity["title"]: s for s in scored}
    assert by_title["Park visit"].budget_match > by_title["Fine dining"].budget_match


def test_recommendation_engine_interest_match_keyword_overlap():
    engine = RecommendationEngine(ContextEngine())
    museum = {"time": "10:00 AM", "title": "Art Museum", "description": "Modern art collection", "estimated_cost": 10}
    generic = {"time": "11:00 AM", "title": "City Walk", "description": "General stroll", "estimated_cost": 0}

    preferences = UserPreferences(interests=["art", "museums"])
    scored = engine.score_and_rank([museum, generic], preferences, daily_budget_hint=50)

    by_title = {s.activity["title"]: s for s in scored}
    assert by_title["Art Museum"].interest_match > by_title["City Walk"].interest_match


def test_recommendation_engine_no_interests_is_neutral_not_penalized():
    engine = RecommendationEngine(ContextEngine())
    activity = {"time": "10:00 AM", "title": "Anything", "description": "Some activity", "estimated_cost": 10}

    scored = engine.score_and_rank([activity], UserPreferences(interests=[]), daily_budget_hint=50)

    assert scored[0].interest_match == 0.5


def test_explainability_engine_cites_high_interest_match():
    from app.cognitive.recommendation_engine import ScoredActivity

    engine = ExplainabilityEngine()
    scored = ScoredActivity(
        activity={"title": "Art Museum"},
        budget_match=0.9,
        interest_match=0.9,
        context=ContextEngine().score_activity({"time": "10:00 AM"}),
    )

    explanation = engine.explain(scored)

    assert "interests" in explanation.reason_text.lower()
    assert "budget" in explanation.reason_text.lower()
    assert 0 < explanation.confidence <= 1.0


def test_risk_assessment_engine_returns_neutral_score():
    engine = RiskAssessmentEngine()
    assert engine.score_trip([{"day_number": 1}]) == 0.5
