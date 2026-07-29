"""
Explainability Engine for SmartTrip AI (SCIF Framework).

Generates transparent, grounded explanations for every recommendation.
Every claim in reason_text/supporting_evidence must trace to a real
computed value - the previous version claimed "verified by safety
monitoring engine" and "ideal weather forecast... verified by Open-Meteo"
unconditionally, when safety has no real data source at all (see
context_engine.py) and weather is only real when destination coordinates
were actually available. Explanations now only cite a factor as a reason
when ContextEngine itself reports that factor as available - never claim
verification of something that wasn't actually verified.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.cognitive.recommendation_engine import ScoredActivity


@dataclass
class Explanation:
    reason_text: str
    budget_match: float
    interest_match: float
    weather_match: float
    context_score: float
    confidence: float
    supporting_evidence: list[str]
    unavailable_factors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason_text": self.reason_text,
            "budget_match": round(self.budget_match, 2),
            "interest_match": round(self.interest_match, 2),
            "weather_match": round(self.weather_match, 2),
            "context_score": round(self.context_score, 2),
            "confidence": round(self.confidence, 2),
            "supporting_evidence": self.supporting_evidence,
            "unavailable_factors": self.unavailable_factors,
        }


class ExplainabilityEngine:
    def explain(self, scored: ScoredActivity) -> Explanation:
        reasons: list[str] = []
        evidence: list[str] = []
        context = scored.context
        weather_available = "weather" not in context.unavailable_components

        if scored.interest_match >= 0.75:
            reasons.append("strongly matches your declared interests")
            evidence.append(f"Interest overlap score: {round(scored.interest_match * 100)}%")

        if scored.budget_match >= 0.80:
            reasons.append("fits comfortably within your daily target budget")
            evidence.append(f"Budget fit score: {round(scored.budget_match * 100)}%")

        if weather_available and context.weather_score >= 0.80:
            reasons.append("favorable weather forecast for the planned time")
            evidence.append("Live forecast from Open-Meteo")

        if context.opening_hours_score >= 0.90:
            reasons.append("scheduled during typical opening hours")

        if not reasons:
            reasons.append("a balanced recommendation based on budget and interest fit")
            evidence.append("Balanced score across available cognitive filters")

        reason_text = "; ".join(reasons).capitalize() + "."

        # Confidence is an average of only the factors that are actually
        # real for this activity (budget, interest, always real; weather
        # only if available) - not diluted by, or falsely inflated by,
        # factors with no real data source.
        confidence_factors = [scored.budget_match, scored.interest_match]
        if weather_available:
            confidence_factors.append(context.weather_score)
        confidence = round(sum(confidence_factors) / len(confidence_factors), 2)

        return Explanation(
            reason_text=reason_text,
            budget_match=scored.budget_match,
            interest_match=scored.interest_match,
            weather_match=context.weather_score,
            context_score=context.composite,
            confidence=confidence,
            supporting_evidence=evidence,
            unavailable_factors=scored.unavailable_factors,
        )
