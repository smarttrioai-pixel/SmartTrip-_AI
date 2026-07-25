"""
Explainability Engine for SmartTrip AI (SCIF Framework).
Generates transparent, grounded explanations for every recommendation:
- Reason text
- Budget match
- Interest match
- Distance match
- Popularity score
- Weather match
- Context score
- Safety score
- Overall Confidence
- Supporting Evidence
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
    distance_match: float
    popularity_score: float
    weather_match: float
    context_score: float
    safety_score: float
    confidence: float
    supporting_evidence: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason_text": self.reason_text,
            "budget_match": round(self.budget_match, 2),
            "interest_match": round(self.interest_match, 2),
            "distance_match": round(self.distance_match, 2),
            "popularity_score": round(self.popularity_score, 2),
            "weather_match": round(self.weather_match, 2),
            "context_score": round(self.context_score, 2),
            "safety_score": round(self.safety_score, 2),
            "confidence": round(self.confidence, 2),
            "supporting_evidence": self.supporting_evidence,
        }

class ExplainabilityEngine:
    def explain(self, scored: ScoredActivity) -> Explanation:
        reasons: list[str] = []
        evidence: list[str] = []

        if scored.interest_match >= 0.75:
            reasons.append("strongly matches your declared interests")
            evidence.append(f"Interest overlap score: {round(scored.interest_match * 100)}%")

        if scored.budget_match >= 0.80:
            reasons.append("fits comfortably within your daily target budget")
            evidence.append(f"Budget fit score: {round(scored.budget_match * 100)}%")

        if scored.weather_match >= 0.80:
            reasons.append("ideal weather forecast for outdoor exploration")
            evidence.append("Optimal climate conditions verified by Open-Meteo API")

        if scored.safety_match >= 0.85:
            reasons.append("located in a highly safe, verified zone")
            evidence.append("Low safety risk score verified by safety monitoring engine")

        if not reasons:
            reasons.append("a balanced recommendation tailored to your itinerary parameters")
            evidence.append("Balanced score across multi-factor cognitive filters")

        reason_text = "; ".join(reasons).capitalize() + "."
        confidence = round(
            (scored.budget_match + scored.interest_match + scored.context.composite + scored.safety_match) / 4,
            2,
        )

        return Explanation(
            reason_text=reason_text,
            budget_match=scored.budget_match,
            interest_match=scored.interest_match,
            distance_match=scored.distance_match,
            popularity_score=scored.popularity_score,
            weather_match=scored.weather_match,
            context_score=scored.context.composite,
            safety_score=scored.safety_match,
            confidence=confidence,
            supporting_evidence=evidence,
        )
