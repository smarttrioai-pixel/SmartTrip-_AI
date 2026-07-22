"""
Context Engine (SCIF Section 6, Phase 4 design Section 2.3).

Deliberately partial this phase: opening-hours fit is real (computed from
Gemini's own per-activity output, since no independent POI data source
exists yet). Weather/traffic/crowd/safety return an explicit neutral 0.5
with a flag noting they're unavailable, rather than a fabricated number -
Phase 7 wires in real APIs for these.
"""
from __future__ import annotations

from dataclasses import dataclass, field

NEUTRAL_SCORE = 0.5


@dataclass
class ContextScoreBreakdown:
    opening_hours_score: float
    weather_score: float = NEUTRAL_SCORE
    traffic_score: float = NEUTRAL_SCORE
    crowd_score: float = NEUTRAL_SCORE
    safety_score: float = NEUTRAL_SCORE
    unavailable_components: list[str] = field(
        default_factory=lambda: ["weather", "traffic", "crowd", "safety"]
    )

    @property
    def composite(self) -> float:
        return (
            self.opening_hours_score
            + self.weather_score
            + self.traffic_score
            + self.crowd_score
            + self.safety_score
        ) / 5


class ContextEngine:
    def score_activity(self, activity: dict) -> ContextScoreBreakdown:
        opening_hours_score = self._score_opening_hours(activity)
        return ContextScoreBreakdown(opening_hours_score=opening_hours_score)

    def _score_opening_hours(self, activity: dict) -> float:
        """
        Gemini's own prompt (Planning Engine) asks for a plausible activity
        time; without independent POI opening-hours data (Phase 6+), this
        can only sanity-check the time itself, not verify against a real
        source. Flags obviously implausible late-night/very-early activity
        times as lower-confidence rather than claiming full verification.
        """
        time_str = activity.get("time", "")
        hour = self._parse_hour(time_str)
        if hour is None:
            return NEUTRAL_SCORE
        if 6 <= hour <= 22:
            return 0.9
        return 0.4  # plausible but unusual (very early/late) - not excluded, just scored lower

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
