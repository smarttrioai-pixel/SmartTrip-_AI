"""
SafetyAgent for SmartTrip AI (SCIF Framework).

Wraps RiskAssessmentEngine and performs honest safety analysis.

IMPORTANT DESIGN DECISION:
This project does NOT have access to a live government travel advisory API,
a real-time incident API, or a crowd density API. The SafetyAgent does NOT
fabricate safety alerts.

What SafetyAgent ACTUALLY does:
1. Runs the existing RiskAssessmentEngine (keyword-based heuristic scoring).
2. Clearly labels the result as "internal_heuristic" not real safety data.
3. Marks external safety data as unavailable.
4. Produces honest constraints: generic urban travel precautions.

What SafetyAgent does NOT do:
- It does NOT claim to query a live safety API.
- It does NOT produce fake safety scores that look like real data.
- It does NOT block itinerary generation based on fabricated alerts.

Data sources:
    - RiskAssessmentEngine: keyword-based internal heuristic scoring
    - External safety APIs: UNAVAILABLE (no integration configured)
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app.cognitive.live_context import AgentOutput
from app.cognitive.risk_assessment_engine import RiskAssessmentEngine

logger = logging.getLogger(__name__)


class SafetyAgent:
    """
    SCIF Planning Agent — Safety and Risk Analysis.

    Wraps RiskAssessmentEngine. Runs BEFORE Qwen (heuristic pre-check)
    and again AFTER enrichment (scoring the actual itinerary).

    Clearly separates:
        REAL EXTERNAL DATA:  unavailable
        INTERNAL HEURISTIC:  keyword-based risk scoring (what we have)
    """

    def __init__(self, risk_engine: RiskAssessmentEngine) -> None:
        self._risk = risk_engine

    async def pre_check(
        self,
        destination: str,
        travel_style: str = "balanced",
        interests: list[str] | None = None,
    ) -> tuple[dict[str, Any], list[str], AgentOutput]:
        """
        Run a pre-generation safety check for the destination.

        Returns:
            (risk_info: dict, constraints: list[str], AgentOutput)

        The risk_info dict contains ONLY internal heuristic data.
        """
        t0 = time.monotonic()
        interests = interests or []

        # Run the real destination risk evaluation (heuristic)
        risk_info = self._risk.evaluate_destination_risk(destination)

        # Build honest safety constraints
        constraints = self._build_safety_constraints(destination, travel_style)

        latency_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "SAFETY_AGENT destination=%r risk_score=%.2f source=internal_heuristic",
            destination, risk_info.get("overall_risk_score", 0.0),
        )

        agent_output = AgentOutput(
            agent_name="SafetyAgent",
            status="ok",
            data_source="internal_heuristic",
            contribution_summary=(
                f"Safety assessment (heuristic): "
                f"{risk_info.get('safety_level', 'Unknown')} for {destination}. "
                f"Note: No live safety API is integrated; this is a keyword-based estimate."
            ),
            items_returned=len(constraints),
            latency_ms=latency_ms,
            details={
                "source_type": "internal_heuristic",
                "external_safety_api": "unavailable",
                "overall_risk_score": risk_info.get("overall_risk_score"),
                "safety_level": risk_info.get("safety_level"),
                "constraints_count": len(constraints),
            },
        )

        return risk_info, constraints, agent_output

    def score_itinerary(self, days: list[dict], destination: str) -> float:
        """
        Score a completed itinerary. Called after place enrichment.
        Returns composite risk score 0.0–1.0.
        """
        return self._risk.score_trip(days, destination=destination)

    @staticmethod
    def _build_safety_constraints(destination: str, travel_style: str) -> list[str]:
        """Build generic, honest safety constraints."""
        constraints: list[str] = []

        constraints.append(
            f"Apply standard urban travel safety precautions for {destination}. "
            "Avoid isolated areas after dark."
        )

        if travel_style in ("adventure", "extreme"):
            constraints.append(
                "Adventure activities carry inherent risk. Include only activities "
                "with established safety records. Avoid unguided extreme activities."
            )

        constraints.append(
            "Note: Real-time safety data (incidents, advisories) is not available "
            "in this system. Recommend users check official travel advisories."
        )

        return constraints
