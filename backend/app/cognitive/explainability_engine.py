"""
Explainability Engine (SCIF Section 6, Phase 4 design Section 2.6).

Templated, not freely LLM-generated - every explanation is assembled from
score thresholds on values the Recommendation/Context Engines actually
computed. This is what makes the explanation traceable rather than a
plausible-sounding post-hoc rationalization.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.cognitive.recommendation_engine import ScoredActivity


@dataclass
class Explanation:
    reason_text: str
    budget_match: float
    interest_match: float
    context_score: float
    confidence: float

    def to_dict(self) -> dict:
        return {
            "reason_text": self.reason_text,
            "budget_match": round(self.budget_match, 2),
            "interest_match": round(self.interest_match, 2),
            "context_score": round(self.context_score, 2),
            "confidence": round(self.confidence, 2),
        }


class ExplainabilityEngine:
    def explain(self, scored: ScoredActivity) -> Explanation:
        reasons: list[str] = []

        if scored.interest_match >= 0.7:
            reasons.append("matches your stated interests")
        elif scored.interest_match <= 0.3:
            reasons.append("a suggestion outside your usual interests, for variety")

        if scored.budget_match >= 0.8:
            reasons.append("fits comfortably within your budget")
        elif scored.budget_match <= 0.3:
            reasons.append("runs above your typical budget for this trip")

        if scored.context.opening_hours_score >= 0.8:
            reasons.append("scheduled at a typical, well-supported time")

        if not reasons:
            reasons.append("a balanced fit based on your trip parameters")

        reason_text = "; ".join(reasons).capitalize() + "."

        # Confidence is a straight average of the 3 components this phase.
        # Phase 6 folds in the remaining pipeline stages' scores here -
        # this number is expected to become more granular, not more correct;
        # it's an honest partial signal now, not a placeholder.
        confidence = (scored.budget_match + scored.interest_match + scored.context.composite) / 3

        return Explanation(
            reason_text=reason_text,
            budget_match=scored.budget_match,
            interest_match=scored.interest_match,
            context_score=scored.context.composite,
            confidence=confidence,
        )
