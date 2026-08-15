"""
Live Context Engine for SmartTrip AI SCIF Layer.

Responsibilities:
    1. Build LiveContext by collecting real-world data:
           Weather      → WeatherService (Open-Meteo daily forecast)
           Opening hrs  → parsed from Geoapify enrichment results
           Date/time    → IST (Asia/Kolkata), timezone-aware

    2. Evaluate activities and emit CognitiveDecision objects:
           "reject"     → place closed on scheduled day, or unverified
           "reschedule" → outdoor activity during rain/storm window
           "warn"       → marginal conditions
           "approve"    → passes all checks

    3. Derive human-readable planning constraints for the Qwen prompt.

Design rules:
    - This engine DECIDES. Qwen GENERATES.
    - External provider data (Open-Meteo, Geoapify) is always authoritative
      over LLM assumptions.
    - If a data source is unavailable, no decision is made based on it.
      Do not reject/reschedule based on missing data.
    - All decisions are logged with structured fields for auditability.

Priority of decisions when multiple apply to one activity:
    reject > reschedule > warn > approve

Opening hours source: Geoapify place data (field "opening_hours" in
PlaceEnrichmentResult). Parsed using lightweight OSM hours parser
(handles Mo-Su day ranges and HH:MM-HH:MM time ranges).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone

from app.cognitive.live_context import (
    CognitiveContext,
    CognitiveDecision,
    LiveContext,
    OpeningHoursSnapshot,
    WeatherSnapshot,
)
from app.integrations.weather_service import WeatherService

logger = logging.getLogger(__name__)

# IST offset
_IST = timezone(timedelta(hours=5, minutes=30))

# Categories considered "outdoor" — weather affects these
_OUTDOOR_CATEGORIES = frozenset({
    "attraction", "nature", "culture", "sights", "museum",
    "beach", "park", "outdoor", "sports", "adventure",
})

# Rain probability threshold above which outdoor activities are rescheduled
_RAIN_RESCHEDULE_THRESHOLD = 0.70

# Rain probability threshold above which we emit a warn (below reschedule)
_RAIN_WARN_THRESHOLD = 0.45

# Morning safe slot to reschedule to when afternoon/evening rain is forecast
_MORNING_SAFE_SLOT = "07:00 AM"

# OSM weekday abbreviations → index (0=Mo, 6=Su) matching date.weekday()
_WEEKDAY_MAP = {"Mo": 0, "Tu": 1, "We": 2, "Th": 3, "Fr": 4, "Sa": 5, "Su": 6}
_WEEKDAY_ABBR = {v: k for k, v in _WEEKDAY_MAP.items()}


# -----------------------------------------------------------------------
# Opening-hours OSM format parser
# -----------------------------------------------------------------------

def _parse_osm_hours(raw: str, check_date: date, check_time_str: str) -> str:
    """
    Parse an OSM-format opening_hours string and determine if the place is
    open on check_date at check_time_str.

    Returns: "open" | "closed" | "unknown"

    Supports common formats:
        "Mo-Fr 09:00-18:00"
        "Mo-Sa 10:00-20:00; Su 12:00-18:00"
        "24/7"
        "Tu-Su 10:00-17:00"
        "Mo,We,Fr 08:00-12:00"

    Unsupported or unparseable formats → "unknown" (never "open" by default).
    """
    if not raw or not raw.strip():
        return "unknown"

    raw = raw.strip()
    if raw == "24/7":
        return "open"

    weekday = check_date.weekday()  # 0=Mon, 6=Sun
    check_hour = _parse_hhmm(check_time_str)
    if check_hour is None:
        return "unknown"

    # Split on semicolons for multiple rule segments
    segments = [s.strip() for s in raw.split(";")]
    for segment in segments:
        try:
            result = _evaluate_segment(segment, weekday, check_hour)
            if result is not None:
                return "open" if result else "closed"
        except Exception:
            continue

    return "unknown"


def _evaluate_segment(segment: str, weekday: int, check_hour: float) -> bool | None:
    """
    Evaluate one OSM hours segment like "Mo-Fr 09:00-18:00".
    Returns True (open), False (closed), or None (segment doesn't match this day).
    """
    seg = segment.strip()

    # Handle explicit "<days> closed" segments (e.g. "Mo closed", "Mo 09:00-17:00 closed")
    # Strip time portion if present and check if day matches
    if "closed" in seg.lower():
        # Remove any time range and 'closed' keyword, keep day spec
        day_part = re.sub(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}", "", seg)
        day_part = re.sub(r"closed", "", day_part, flags=re.IGNORECASE).strip()
        if not day_part or _day_matches(day_part, weekday):
            return False
        return None

    # Match pattern: [day_spec] HH:MM-HH:MM
    m = re.match(
        r"^((?:[A-Z][a-z][-,A-Za-z]*)\s+)?(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*$",
        seg,
    )
    if not m:
        return None

    day_spec = (m.group(1) or "").strip()
    open_time = _parse_hhmm(m.group(2))
    close_time = _parse_hhmm(m.group(3))

    if open_time is None or close_time is None:
        return None

    # If no day spec, applies to all days
    if day_spec and not _day_matches(day_spec, weekday):
        return None

    return open_time <= check_hour < close_time


def _day_matches(day_spec: str, weekday: int) -> bool:
    """Check if weekday matches the OSM day spec (e.g. "Mo-Fr", "Tu-Su", "Mo,We,Fr")."""
    if not day_spec:
        return True
    day_spec = day_spec.strip()
    # Comma-separated list: "Mo,We,Fr"
    if "," in day_spec:
        parts = [p.strip() for p in day_spec.split(",")]
        return any(_single_day_matches(p, weekday) for p in parts)
    # Range: "Mo-Fr" or "Tu-Su"
    if "-" in day_spec:
        parts = day_spec.split("-")
        if len(parts) == 2:
            start = _WEEKDAY_MAP.get(parts[0].strip()[:2])
            end = _WEEKDAY_MAP.get(parts[1].strip()[:2])
            if start is not None and end is not None:
                if start <= end:
                    return start <= weekday <= end
                else:  # wrap-around e.g. "Fr-Mo"
                    return weekday >= start or weekday <= end
    return _single_day_matches(day_spec, weekday)


def _single_day_matches(day: str, weekday: int) -> bool:
    d = day.strip()[:2]
    idx = _WEEKDAY_MAP.get(d)
    return idx == weekday if idx is not None else False


def _parse_hhmm(time_str: str) -> float | None:
    """Parse "HH:MM" or "H:MM AM/PM" to float hours (e.g. 14.5 = 14:30)."""
    if not time_str:
        return None
    time_str = time_str.strip()
    # Handle AM/PM
    upper = time_str.upper()
    is_pm = "PM" in upper
    is_am = "AM" in upper
    time_str = re.sub(r"[AaPpMm\s]", "", time_str)
    parts = time_str.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        if is_pm and hour != 12:
            hour += 12
        if is_am and hour == 12:
            hour = 0
        return hour + minute / 60.0
    except (ValueError, IndexError):
        return None


# -----------------------------------------------------------------------
# LiveContextEngine
# -----------------------------------------------------------------------

class LiveContextEngine:
    """
    Builds LiveContext from real providers and evaluates activities
    to emit CognitiveDecision objects.

    External data sources:
        WeatherService      → Open-Meteo daily forecast
        Geoapify            → opening_hours (passed in via enrichment results)

    This class makes decisions. Qwen generates the itinerary text.
    """

    def __init__(self, weather_service: WeatherService) -> None:
        self._weather = weather_service

    # ------------------------------------------------------------------
    # Build LiveContext (before Qwen)
    # ------------------------------------------------------------------

    async def build_live_context(
        self,
        destination: str,
        lat: float,
        lon: float,
        start_date: date,
        end_date: date,
    ) -> LiveContext:
        """
        Fetch real-world data for all travel dates.
        Called BEFORE Qwen generates the itinerary so weather constraints
        can be injected into the prompt.
        """
        live = LiveContext(
            travel_start_date=start_date,
            travel_end_date=end_date,
            current_datetime=datetime.now(tz=_IST),
            unavailable_sources=["traffic", "events"],
        )

        # Fetch weather for each travel date
        current_date = start_date
        weather_available = False
        while current_date <= end_date:
            snapshot_raw = await self._weather.get_forecast_for_date(lat, lon, current_date)
            snap = WeatherSnapshot(
                date=current_date,
                status=snapshot_raw.get("status", "unavailable"),
                condition=snapshot_raw.get("condition"),
                temperature_max=snapshot_raw.get("temperature_max"),
                temperature_min=snapshot_raw.get("temperature_min"),
                rain_probability=snapshot_raw.get("rain_probability"),
                precipitation_mm=snapshot_raw.get("precipitation_mm"),
                wind_speed=snapshot_raw.get("wind_speed"),
                is_suitable_outdoor=snapshot_raw.get("is_suitable_outdoor", True),
                suitability_score=snapshot_raw.get("suitability_score", 0.5),
                source=snapshot_raw.get("source", "unavailable"),
                reason=snapshot_raw.get("reason"),
            )
            live.weather_by_date[current_date] = snap
            if snap.status == "available":
                weather_available = True
            current_date += timedelta(days=1)

        if weather_available:
            live.available_sources.append("weather")
        else:
            live.unavailable_sources.append("weather")

        logger.info(
            "SCIF_CONTEXT_BUILT destination=%s lat=%.4f lon=%.4f "
            "travel_dates=%s_to_%s weather_status=%s available_sources=%s",
            destination, lat, lon,
            start_date.isoformat(), end_date.isoformat(),
            "available" if weather_available else "unavailable",
            live.available_sources,
        )
        return live

    # ------------------------------------------------------------------
    # Populate opening hours from Geoapify enrichment results (post-enrichment)
    # ------------------------------------------------------------------

    def ingest_opening_hours(
        self,
        live: LiveContext,
        enrichment_results: list[dict],
        travel_date: date,
        activity_time_str: str,
    ) -> None:
        """
        Parse opening_hours from Geoapify place enrichment results and
        populate live.opening_hours. Called after PlaceEnrichmentService
        returns results for each activity.

        enrichment_results: list of enriched activity dicts with
            place_enrichment.opening_hours (from Geoapify)
        """
        for result in enrichment_results:
            enrichment = result.get("place_enrichment") or {}
            place_id = enrichment.get("source_id") or ""
            place_name = enrichment.get("matched_place_name") or result.get("title", "")
            raw_hours = enrichment.get("opening_hours")

            if not place_id:
                continue

            weekday_idx = travel_date.weekday()
            weekday_abbr = _WEEKDAY_ABBR.get(weekday_idx, "Mo")

            if raw_hours:
                status = _parse_osm_hours(raw_hours, travel_date, activity_time_str)
                is_open = {"open": True, "closed": False}.get(status)
                source = "geoapify"
                live.available_sources = list(
                    set(live.available_sources) | {"opening_hours"}
                )
            else:
                status = "unknown"
                is_open = None
                source = "unavailable"

            snap = OpeningHoursSnapshot(
                place_id=place_id,
                place_name=place_name,
                raw_hours=raw_hours,
                status=status,
                is_open=is_open,
                checked_date=travel_date,
                checked_weekday=weekday_abbr,
                source=source,
            )
            live.opening_hours[place_id] = snap

    # ------------------------------------------------------------------
    # Evaluate activities → CognitiveDecision[]
    # ------------------------------------------------------------------

    def evaluate_activities(
        self,
        days: list[dict],
        live: LiveContext,
        start_date: date,
    ) -> list[CognitiveDecision]:
        """
        Walk every activity in every day and emit explicit CognitiveDecisions.

        Called TWICE in the pipeline:
            Pass 1 (pre-Qwen): weather decisions only → injected into prompt
            Pass 2 (post-Geoapify): opening-hours decisions → applied to plan

        The higher-priority decision (reject > reschedule > warn > approve)
        wins when multiple decisions apply to the same activity.
        """
        decisions: list[CognitiveDecision] = []

        for day_idx, day in enumerate(days):
            activity_date = start_date + timedelta(days=day_idx)
            weather = live.weather_by_date.get(activity_date)

            for activity in day.get("activities", []):
                title = str(activity.get("title") or "")
                category = str(activity.get("category") or "").lower()
                time_str = str(activity.get("time") or "")
                place_id = (
                    (activity.get("place_enrichment") or {}).get("source_id") or ""
                )

                decision: CognitiveDecision | None = None

                # --------------------------------------------------------
                # Check 1: Opening hours (reject if confirmed closed)
                # --------------------------------------------------------
                if place_id and place_id in live.opening_hours:
                    oh = live.opening_hours[place_id]
                    if oh.status == "closed":
                        decision = CognitiveDecision(
                            place=title,
                            decision="reject",
                            reason=(
                                f"Confirmed closed on {activity_date.strftime('%A')} "
                                f"({oh.checked_weekday}) per Geoapify opening hours"
                            ),
                            evidence={
                                "opening_status": "closed",
                                "raw_hours": oh.raw_hours,
                                "checked_date": activity_date.isoformat(),
                                "source": "geoapify",
                            },
                            confidence=1.0,
                        )
                        logger.info(
                            "SCIF_DECISION place=%r decision=reject "
                            "reason=closed_hours date=%s source=geoapify",
                            title, activity_date.isoformat(),
                        )

                # --------------------------------------------------------
                # Check 2: Weather (outdoor categories only)
                # --------------------------------------------------------
                if decision is None and weather and weather.status == "available":
                    is_outdoor = category in _OUTDOOR_CATEGORIES or any(
                        kw in title.lower() for kw in
                        ["beach", "park", "garden", "outdoor", "trek", "trail",
                         "lake", "river", "coast", "hilltop", "fort", "lighthouse"]
                    )

                    if is_outdoor:
                        rain_prob = weather.rain_probability or 0.0
                        condition = weather.condition or ""

                        if "Thunderstorm" in condition:
                            decision = CognitiveDecision(
                                place=title,
                                decision="reject",
                                reason="Thunderstorm forecast — outdoor activity unsafe",
                                evidence={
                                    "condition": condition,
                                    "rain_probability": rain_prob,
                                    "date": activity_date.isoformat(),
                                    "source": "open-meteo",
                                },
                                confidence=0.95,
                            )
                            logger.info(
                                "SCIF_DECISION place=%r decision=reject "
                                "reason=thunderstorm date=%s condition=%s rain_prob=%.2f",
                                title, activity_date.isoformat(), condition, rain_prob,
                            )

                        elif rain_prob >= _RAIN_RESCHEDULE_THRESHOLD:
                            # If activity is already in safe morning window, approve
                            activity_hour = _parse_hhmm(time_str) or 12.0
                            if activity_hour < 9.0:
                                decision = CognitiveDecision(
                                    place=title,
                                    decision="approve",
                                    reason="Scheduled in early morning — rain expected later",
                                    evidence={
                                        "rain_probability": rain_prob,
                                        "condition": condition,
                                        "source": "open-meteo",
                                    },
                                    confidence=0.85,
                                )
                            else:
                                decision = CognitiveDecision(
                                    place=title,
                                    decision="reschedule",
                                    reason=(
                                        f"High rain probability ({int(rain_prob * 100)}%) "
                                        f"forecast — move outdoor visit to morning"
                                    ),
                                    evidence={
                                        "rain_probability": rain_prob,
                                        "condition": condition,
                                        "date": activity_date.isoformat(),
                                        "source": "open-meteo",
                                    },
                                    confidence=0.90,
                                    suggested_time=_MORNING_SAFE_SLOT,
                                )
                                logger.info(
                                    "SCIF_DECISION place=%r decision=reschedule "
                                    "reason=heavy_rain date=%s rain_prob=%.2f "
                                    "suggested_time=%s",
                                    title, activity_date.isoformat(),
                                    rain_prob, _MORNING_SAFE_SLOT,
                                )

                        elif rain_prob >= _RAIN_WARN_THRESHOLD or not weather.is_suitable_outdoor:
                            decision = CognitiveDecision(
                                place=title,
                                decision="warn",
                                reason=(
                                    f"Moderate rain risk ({int(rain_prob * 100)}%) "
                                    f"— plan for possible light rain"
                                ),
                                evidence={
                                    "rain_probability": rain_prob,
                                    "condition": condition,
                                    "source": "open-meteo",
                                },
                                confidence=0.75,
                            )

                # Default: approve (no issues found)
                if decision is None:
                    decision = CognitiveDecision(
                        place=title,
                        decision="approve",
                        reason="No weather or hours issues detected",
                        evidence={"source": "scif"},
                        confidence=0.80,
                    )

                decisions.append(decision)

        return decisions

    # ------------------------------------------------------------------
    # Derive human-readable planning constraints for the Qwen prompt
    # ------------------------------------------------------------------

    def derive_constraints(
        self,
        live: LiveContext,
        start_date: date,
        end_date: date,
    ) -> list[str]:
        """
        Translate live context into human-readable planning constraints
        that will be injected into the Qwen itinerary prompt.

        These represent FACTS from external providers.
        Qwen must not override them.
        """
        constraints: list[str] = []
        current = start_date
        day_num = 1
        while current <= end_date:
            snap = live.weather_by_date.get(current)
            if snap and snap.status == "available":
                rain_prob = snap.rain_probability or 0.0
                cond = snap.condition or "Unknown"
                temp_info = ""
                if snap.temperature_max and snap.temperature_min:
                    temp_info = f" ({snap.temperature_min:.0f}–{snap.temperature_max:.0f}°C)"

                if "Thunderstorm" in cond:
                    constraints.append(
                        f"Day {day_num} ({current.strftime('%b %d')}): Thunderstorm forecast{temp_info}. "
                        f"AVOID all outdoor activities. Schedule indoor alternatives only."
                    )
                elif rain_prob >= _RAIN_RESCHEDULE_THRESHOLD:
                    constraints.append(
                        f"Day {day_num} ({current.strftime('%b %d')}): Heavy rain forecast "
                        f"({int(rain_prob*100)}% probability), {cond}{temp_info}. "
                        f"Schedule outdoor activities before 09:00 AM only. Use indoor alternatives in afternoon."
                    )
                elif rain_prob >= _RAIN_WARN_THRESHOLD:
                    constraints.append(
                        f"Day {day_num} ({current.strftime('%b %d')}): Moderate rain risk "
                        f"({int(rain_prob*100)}%){temp_info}. Prefer morning for outdoor activities."
                    )
                elif not snap.is_suitable_outdoor:
                    constraints.append(
                        f"Day {day_num} ({current.strftime('%b %d')}): {cond}{temp_info}. "
                        f"Consider indoor alternatives for outdoor activities."
                    )
            current += timedelta(days=1)
            day_num += 1

        if not constraints and "weather" not in live.available_sources:
            constraints.append(
                "Weather data unavailable for this date range — plan for typical conditions."
            )

        return constraints

    # ------------------------------------------------------------------
    # Build CognitiveContext (final assembly after all stages)
    # ------------------------------------------------------------------

    def build_cognitive_context(
        self,
        request_dict: dict,
        memory_items: int,
        memory_summary: str,
        live: LiveContext,
        constraints: list[str],
        decisions: list[CognitiveDecision],
    ) -> CognitiveContext:
        return CognitiveContext(
            current_request=request_dict,
            memory_items=memory_items,
            memory_summary=memory_summary,
            live_context=live,
            constraints=constraints,
            decisions=decisions,
        )


_live_context_engine: LiveContextEngine | None = None


def get_live_context_engine() -> LiveContextEngine:
    global _live_context_engine
    if _live_context_engine is None:
        from app.integrations.weather_service import get_weather_service
        _live_context_engine = LiveContextEngine(get_weather_service())
    return _live_context_engine
