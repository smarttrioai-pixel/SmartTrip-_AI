"""
WeatherAgent for SmartTrip AI (SCIF Framework).

Thin agent interface around LiveContextEngine / WeatherService.
Responsible for fetching real weather forecasts for the exact travel dates
and translating them into structured planning constraints.

Data source: Open-Meteo (via WeatherService / LiveContextEngine)

Design rules:
- Always fetch for the ACTUAL requested travel dates, never a default city.
- If geocoding fails → weather unavailable, mark as such. Never fabricate.
- Constraints must be actionable for Qwen (not just display strings).
"""
from __future__ import annotations

import logging
import time
from datetime import date

from app.cognitive.live_context import AgentOutput, LiveContext
from app.cognitive.live_context_engine import LiveContextEngine

logger = logging.getLogger(__name__)


class WeatherAgent:
    """
    SCIF Planning Agent — Weather Fetch and Constraint Derivation.

    Wraps LiveContextEngine. Runs BEFORE Qwen.
    Produces LiveContext + weather constraints + AgentOutput.
    """

    def __init__(self, live_context_engine: LiveContextEngine) -> None:
        self._engine = live_context_engine

    async def fetch_and_constrain(
        self,
        destination: str,
        lat: float | None,
        lon: float | None,
        start_date: date,
        end_date: date,
    ) -> tuple[LiveContext, list[str], AgentOutput]:
        """
        Fetch weather for travel dates and derive planning constraints.

        Returns:
            (LiveContext, constraints: list[str], AgentOutput)
            LiveContext.weather_by_date is populated from Open-Meteo.
            If lat/lon is None, returns an unavailable LiveContext.
        """
        t0 = time.monotonic()

        if lat is None or lon is None:
            # Geocoding failed — cannot fetch weather
            latency_ms = (time.monotonic() - t0) * 1000
            live_ctx = LiveContext()
            agent_output = AgentOutput(
                agent_name="WeatherAgent",
                status="unavailable",
                data_source="Open-Meteo",
                contribution_summary=(
                    "Weather unavailable: destination coordinates not resolved."
                ),
                items_returned=0,
                latency_ms=latency_ms,
                details={"reason": "geocoding_failed"},
            )
            logger.warning(
                "WEATHER_AGENT destination=%r lat/lon missing → unavailable",
                destination,
            )
            return live_ctx, [], agent_output

        try:
            live_ctx = await self._engine.build_live_context(
                destination=destination,
                lat=lat,
                lon=lon,
                start_date=start_date,
                end_date=end_date,
            )
            constraints = self._engine.derive_constraints(
                live_ctx, start_date, end_date
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "WEATHER_AGENT destination=%r error: %s", destination, exc
            )
            live_ctx = LiveContext()
            agent_output = AgentOutput(
                agent_name="WeatherAgent",
                status="error",
                data_source="Open-Meteo",
                contribution_summary=f"Weather fetch failed: {exc}",
                items_returned=0,
                latency_ms=latency_ms,
                details={"error": str(exc)},
            )
            return live_ctx, [], agent_output

        latency_ms = (time.monotonic() - t0) * 1000
        weather_days = len(live_ctx.weather_by_date)

        # Build contribution summary from actual weather data
        if weather_days > 0:
            conditions = [
                snap.condition or "Unknown"
                for snap in live_ctx.weather_by_date.values()
                if snap.condition
            ]
            condition_str = ", ".join(set(conditions)) if conditions else "mixed"
            contribution = (
                f"{weather_days} day(s) forecast obtained. "
                f"Conditions: {condition_str}. "
                f"{len(constraints)} planning constraint(s) derived."
            )
        else:
            contribution = "Weather data unavailable for travel dates."

        logger.info(
            "WEATHER_AGENT destination=%r days=%d constraints=%d latency_ms=%.0f",
            destination, weather_days, len(constraints), latency_ms,
        )

        agent_output = AgentOutput(
            agent_name="WeatherAgent",
            status="ok" if weather_days > 0 else "unavailable",
            data_source="Open-Meteo",
            contribution_summary=contribution,
            items_returned=weather_days,
            latency_ms=latency_ms,
            details={
                "weather_days": weather_days,
                "constraints_count": len(constraints),
                "available_sources": live_ctx.available_sources,
            },
        )

        return live_ctx, constraints, agent_output
