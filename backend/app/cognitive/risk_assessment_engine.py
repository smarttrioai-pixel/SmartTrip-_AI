"""
Risk Assessment Engine (SCIF Section 6, Phase 4 design Section 2.8).

Deliberately the thinnest engine this phase - no safety/health/crowd data
source exists yet (Phase 7). Exists now purely so `risk_score` is a real
field on every trip from day one rather than a later schema migration.
"""
from __future__ import annotations

NEUTRAL_RISK_SCORE = 0.5


class RiskAssessmentEngine:
    def score_trip(self, days: list[dict]) -> float:
        """Returns a neutral score for every trip until Phase 7 wires in real signals."""
        return NEUTRAL_RISK_SCORE
