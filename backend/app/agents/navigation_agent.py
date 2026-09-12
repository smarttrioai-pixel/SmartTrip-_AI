"""
NavigationAgent for SmartTrip AI (SCIF Framework).

Thin agent interface around NavigationService (Geoapify geocoding).
Responsible for resolving destination coordinates and deriving
geographic planning constraints.

Data source: Geoapify Geocoding API (via NavigationService)

Design rules:
- If geocoding fails, coordinates are None. Never fabricate lat/lon.
- Constraints are practical geographic rules for Qwen.
- Also provides a basic "geographic feasibility" note to help Qwen avoid
  impossible itinerary sequences.
"""
from __future__ import annotations

import logging
import time

from app.cognitive.live_context import AgentOutput
from app.integrations.navigation_service import NavigationService

logger = logging.getLogger(__name__)


class NavigationAgent:
    """
    SCIF Planning Agent — Destination Geocoding and Navigation Constraints.

    Wraps NavigationService. Runs BEFORE Qwen.
    Resolves destination lat/lon and derives location-based constraints.
    """

    def __init__(self, navigation_service: NavigationService) -> None:
        self._nav = navigation_service

    async def resolve_destination(
        self,
        destination: str,
        transport: str = "any",
    ) -> tuple[float | None, float | None, list[str], AgentOutput]:
        """
        Geocode the destination and derive navigation constraints.

        Returns:
            (lat, lon, constraints: list[str], AgentOutput)
            lat/lon are None if geocoding fails.
        """
        t0 = time.monotonic()

        lat: float | None = None
        lon: float | None = None

        try:
            geocode_result = await self._nav.geocode(destination)
            if geocode_result:
                lat = geocode_result.get("lat")
                lon = geocode_result.get("lon")
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "NAVIGATION_AGENT destination=%r geocode_error: %s", destination, exc
            )
            agent_output = AgentOutput(
                agent_name="NavigationAgent",
                status="error",
                data_source="Geoapify",
                contribution_summary=f"Geocoding failed: {exc}",
                items_returned=0,
                latency_ms=latency_ms,
                details={"error": str(exc)},
            )
            return None, None, [], agent_output

        latency_ms = (time.monotonic() - t0) * 1000

        if lat is None or lon is None:
            logger.warning(
                "NAVIGATION_AGENT destination=%r → no coordinates returned",
                destination,
            )
            agent_output = AgentOutput(
                agent_name="NavigationAgent",
                status="unavailable",
                data_source="Geoapify",
                contribution_summary=(
                    f"Could not resolve coordinates for '{destination}'. "
                    "Weather and location-aware planning will be limited."
                ),
                items_returned=0,
                latency_ms=latency_ms,
                details={"destination": destination},
            )
            return None, None, [], agent_output

        # Build geographic constraints
        constraints = self._build_geographic_constraints(destination, transport)

        logger.info(
            "NAVIGATION_AGENT destination=%r lat=%.4f lon=%.4f constraints=%d latency_ms=%.0f",
            destination, lat, lon, len(constraints), latency_ms,
        )

        agent_output = AgentOutput(
            agent_name="NavigationAgent",
            status="ok",
            data_source="Geoapify",
            contribution_summary=(
                f"Destination resolved: {destination} → "
                f"lat={lat:.4f}, lon={lon:.4f}. "
                f"{len(constraints)} navigation constraint(s)."
            ),
            items_returned=1,
            latency_ms=latency_ms,
            details={
                "lat": lat,
                "lon": lon,
                "destination": destination,
                "transport": transport,
            },
        )

        return lat, lon, constraints, agent_output

    @staticmethod
    def _build_geographic_constraints(destination: str, transport: str) -> list[str]:
        """Build geographic and transport feasibility constraints."""
        constraints: list[str] = []

        # Geographic coherence constraint
        constraints.append(
            f"All activities must be geographically reachable within {destination} "
            f"or its immediate surroundings. Do NOT plan day trips to distant cities "
            f"unless explicitly requested by the user."
        )

        # Transport constraint
        if transport == "any" or not transport:
            constraints.append(
                "Transport mode is flexible. Plan activities in geographic clusters "
                "to minimize travel time between consecutive venues."
            )
        elif transport in ("walking", "foot"):
            constraints.append(
                "User prefers walking. Keep consecutive activities within 1–2 km of each other."
            )
        elif transport in ("car", "auto", "taxi"):
            constraints.append(
                "User has private transport. Moderate travel distances are acceptable. "
                "Cluster morning and afternoon activities to reduce backtracking."
            )
        elif transport in ("train", "rail"):
            constraints.append(
                "User prefers rail travel. Limit day trips to locations with train connectivity."
            )
        elif transport in ("flight", "plane", "air"):
            constraints.append(
                "User prefers flying. For multi-city trips, check airport connectivity."
            )

        # General anti-backtracking constraint
        constraints.append(
            "Schedule activities in a logical geographic sequence within each day. "
            "Avoid routing that requires extensive backtracking between locations."
        )

        return constraints
