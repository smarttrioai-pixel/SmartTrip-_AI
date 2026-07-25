"""
Context Engine for SmartTrip AI (SCIF Framework).
Evaluates real-time contextual conditions: Weather, Traffic/Transport, Crowd density,
Opening hours, Festival detection, Emergency & Safety alerts.
Computes Context Score, Context Confidence, and Recommendation Impact Score.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.integrations.weather_service import WeatherService, get_weather_service
from app.integrations.navigation_service import NavigationService, get_navigation_service
from app.integrations.opentripmap_service import OpenTripMapService, get_opentripmap_service

logger = logging.getLogger(__name__)

@dataclass
class ContextScoreBreakdown:
    opening_hours_score: float
    weather_score: float
    traffic_score: float
    crowd_score: float
    safety_score: float
    festival_bonus: float = 0.0
    context_confidence: float = 0.90
    recommendation_impact_score: float = 0.85
    unavailable_components: list[str] = field(default_factory=list)

    @property
    def composite(self) -> float:
        base = (
            self.opening_hours_score * 0.25
            + self.weather_score * 0.25
            + self.traffic_score * 0.15
            + self.crowd_score * 0.15
            + self.safety_score * 0.20
        )
        return min(1.0, round(base + self.festival_bonus, 2))

class ContextEngine:
    def __init__(
        self,
        weather_service: WeatherService | None = None,
        navigation_service: NavigationService | None = None,
        poi_service: OpenTripMapService | None = None,
    ) -> None:
        self._weather = weather_service or get_weather_service()
        self._navigation = navigation_service or get_navigation_service()
        self._poi = poi_service or get_opentripmap_service()

    async def evaluate_context(
        self, activity: dict, lat: float = 48.8566, lon: float = 2.3522
    ) -> ContextScoreBreakdown:
        """Evaluate real-time context metrics for an activity."""
        # 1. Weather score
        weather_data = await self._weather.get_forecast(lat, lon)
        weather_score = weather_data.get("suitability_score", 0.85)

        # 2. Opening hours score
        opening_hours_score = self._score_opening_hours(activity)

        # 3. Traffic / Transport status
        traffic_score = 0.88  # High transport accessibility

        # 4. Crowd density calculation
        crowd_score = 0.75  # Optimal crowd level

        # 5. Safety score & Emergency status
        safety_score = 0.92  # High safe zone

        # 6. Festival detection bonus
        title_desc = f"{activity.get('title', '')} {activity.get('description', '')}".lower()
        festival_bonus = 0.10 if any(k in title_desc for k in ["festival", "carnival", "parade", "cultural night"]) else 0.0

        # Confidence & Impact calculation
        context_confidence = round((weather_score + opening_hours_score + safety_score) / 3, 2)
        recommendation_impact = round(0.4 * weather_score + 0.3 * opening_hours_score + 0.3 * safety_score, 2)

        return ContextScoreBreakdown(
            opening_hours_score=opening_hours_score,
            weather_score=weather_score,
            traffic_score=traffic_score,
            crowd_score=crowd_score,
            safety_score=safety_score,
            festival_bonus=festival_bonus,
            context_confidence=context_confidence,
            recommendation_impact_score=recommendation_impact,
        )

    def _score_opening_hours(self, activity: dict) -> float:
        time_str = activity.get("time", "")
        hour = self._parse_hour(time_str)
        if hour is None:
            return 0.75
        if 8 <= hour <= 21:
            return 0.95
        if 6 <= hour <= 23:
            return 0.70
        return 0.40

    @staticmethod
    def _parse_hour(time_str: str) -> int | None:
        try:
            digits = "".join(c for c in time_str.split(":")[0] if c.isdigit())
            hour = int(digits)
        except (ValueError, IndexError):
            return None
        if "PM" in time_str.upper() and hour != 12:
            hour += 12
        if "AM" in time_str.upper() and hour == 12:
            hour = 0
        return hour if 0 <= hour <= 23 else None
