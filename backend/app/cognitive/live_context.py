"""
Live Context types for SmartTrip AI SCIF Layer.

These dataclasses represent the FOUR clearly-separated context types:

    A. current_request   — What is the user asking for right now?
    B. user_memory       — What do we know about this user from history?
    C. retrieved_context — handled separately by MemoryEngine / retrieval
    D. live_context      — What is happening in the real world?

Do NOT merge these into a single generic blob. Source provenance must
always be preserved.

All live data must be sourced from external providers:
    Weather      → Open-Meteo (WeatherService)
    Opening hrs  → Geoapify Places API (GeoapifyProvider)
    Traffic      → unavailable (OSRM is static routing, no live traffic)
    Events       → unavailable (no events API integrated)

If a provider is unavailable, mark status="unavailable". Never fabricate.

CognitiveDecision is the SCIF decision output — each decision traces back
to a specific piece of evidence and can be audited.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


# -----------------------------------------------------------------------
# A. Weather snapshot for one travel date
# -----------------------------------------------------------------------

@dataclass
class WeatherSnapshot:
    """
    Normalized daily weather data for one travel date from Open-Meteo.

    status:
        "available"   — real forecast obtained
        "unavailable" — API failed, date out of range, or past date

    All numeric fields are None when status="unavailable".
    NEVER contains fabricated values.
    """
    date: date
    status: str                     # "available" | "unavailable"
    condition: str | None           # "Clear", "Rainy", "Thunderstorm", …
    temperature_max: float | None   # °C
    temperature_min: float | None   # °C
    rain_probability: float | None  # 0.0–1.0
    precipitation_mm: float | None
    wind_speed: float | None        # km/h
    is_suitable_outdoor: bool       # True = OK for outdoor activities
    suitability_score: float        # 0.0–1.0 (0.9=great, 0.5=neutral, 0.4=bad)
    source: str                     # "open-meteo" | "unavailable"
    reason: str | None = None       # Set only when status="unavailable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "status": self.status,
            "condition": self.condition,
            "temperature_max": self.temperature_max,
            "temperature_min": self.temperature_min,
            "rain_probability": self.rain_probability,
            "precipitation_mm": self.precipitation_mm,
            "wind_speed": self.wind_speed,
            "is_suitable_outdoor": self.is_suitable_outdoor,
            "suitability_score": self.suitability_score,
            "source": self.source,
            "reason": self.reason,
        }


# -----------------------------------------------------------------------
# B. Opening hours snapshot for one place (from Geoapify)
# -----------------------------------------------------------------------

@dataclass
class OpeningHoursSnapshot:
    """
    Opening hours for a verified Geoapify place.

    source: "geoapify" | "unavailable"
    status: "open" | "closed" | "unknown"
        "unknown" means opening_hours data was not available in Geoapify —
        the system does NOT assume open when unknown.
    """
    place_id: str
    place_name: str
    raw_hours: str | None           # e.g. "Mo-Fr 10:00-18:00; Sa 10:00-14:00"
    status: str                     # "open" | "closed" | "unknown"
    is_open: bool | None            # None when status="unknown"
    checked_date: date | None
    checked_weekday: str | None     # "Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"
    source: str                     # "geoapify" | "unavailable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "place_id": self.place_id,
            "place_name": self.place_name,
            "raw_hours": self.raw_hours,
            "status": self.status,
            "is_open": self.is_open,
            "checked_date": self.checked_date.isoformat() if self.checked_date else None,
            "checked_weekday": self.checked_weekday,
            "source": self.source,
        }


# -----------------------------------------------------------------------
# C. SCIF Cognitive Decision — explicit, auditable planning decision
# -----------------------------------------------------------------------

@dataclass
class CognitiveDecision:
    """
    An explicit SCIF planning decision for one place/activity.

    decision:
        "approve"     — place passes all checks, schedule as planned
        "reschedule"  — place is valid but time must change (e.g. avoid rain window)
        "reject"      — place should be removed (closed, unverifiable, etc.)
        "warn"        — place is included but user/planner is warned

    evidence:
        Raw data that drove this decision. Keys vary by decision type:
            weather:   {"rain_probability": 0.85, "condition": "Rainy"}
            hours:     {"opening_status": "closed", "raw_hours": "Tu-Su 09:00-17:00"}
            geoapify:  {"found": false}

    confidence: 0.0–1.0
        Based on source reliability (Geoapify=1.0, Open-Meteo=0.9)

    suggested_time: only set when decision="reschedule"
    """
    place: str
    decision: str                   # "approve" | "reschedule" | "reject" | "warn"
    reason: str
    evidence: dict[str, Any]
    confidence: float               # 0.0–1.0
    suggested_time: str | None = None   # e.g. "07:00 AM" for reschedule

    def to_dict(self) -> dict[str, Any]:
        d = {
            "place": self.place,
            "decision": self.decision,
            "reason": self.reason,
            "evidence": self.evidence,
            "confidence": self.confidence,
        }
        if self.suggested_time:
            d["suggested_time"] = self.suggested_time
        return d


# -----------------------------------------------------------------------
# D. LiveContext — the live-world container
# -----------------------------------------------------------------------

@dataclass
class LiveContext:
    """
    All live/real-world data gathered for this trip planning request.

    weather_by_date:    {date: WeatherSnapshot} — one per travel day
    opening_hours:      {place_id: OpeningHoursSnapshot} — populated
                        post-Geoapify enrichment
    current_datetime:   timezone-aware (IST = Asia/Kolkata)
    available_sources:  ["weather"]  — sources that returned real data
    unavailable_sources: ["traffic", "events"]  — sources with no data
    """
    weather_by_date: dict[date, WeatherSnapshot] = field(default_factory=dict)
    opening_hours: dict[str, OpeningHoursSnapshot] = field(default_factory=dict)
    current_datetime: datetime | None = None
    travel_start_date: date | None = None
    travel_end_date: date | None = None
    available_sources: list[str] = field(default_factory=list)
    unavailable_sources: list[str] = field(default_factory=lambda: ["traffic", "events"])

    def weather_for_date(self, d: date) -> WeatherSnapshot | None:
        return self.weather_by_date.get(d)

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "available_sources": self.available_sources,
            "unavailable_sources": self.unavailable_sources,
            "weather_days": {
                k.isoformat(): v.to_dict()
                for k, v in self.weather_by_date.items()
            },
            "opening_hours_places": len(self.opening_hours),
            "current_datetime": (
                self.current_datetime.isoformat() if self.current_datetime else None
            ),
        }


# -----------------------------------------------------------------------
# E. CognitiveContext — the full cognitive context object
# -----------------------------------------------------------------------

@dataclass
class CognitiveContext:
    """
    The complete cognitive context assembled by LiveContextEngine
    before Qwen generates the itinerary.

    Four types of context are kept SEPARATE to preserve source provenance:

        current_request  — what the user asked for now
        user_memory      — preferences from MemoryEngine
        live_context     — real-world data (weather, opening hours)
        constraints      — human-readable planning constraints derived
                           from live_context by SCIF
        decisions        — explicit CognitiveDecision[] from SCIF
    """
    # A. Current request (summary dict, no sensitive data)
    current_request: dict[str, Any] = field(default_factory=dict)

    # B. User memory summary (memory item count, top preferences text)
    memory_items: int = 0
    memory_summary: str = ""

    # C. Live context
    live_context: LiveContext = field(default_factory=LiveContext)

    # D. Derived planning constraints (human-readable, injected into Qwen prompt)
    constraints: list[str] = field(default_factory=list)

    # E. SCIF decisions
    decisions: list[CognitiveDecision] = field(default_factory=list)

    # F. Place provider trace (Google Places / Geoapify stats)
    # Set by PlanningEngine after Stage 7 enrichment completes.
    provider_trace: dict[str, Any] = field(default_factory=dict)

    def to_trace_dict(self) -> dict[str, Any]:
        """Returns a non-sensitive summary for debug/logging."""
        return {
            "current_request": self.current_request,
            "memory_used": self.memory_items > 0,
            "memory_items": self.memory_items,
            "live_context": self.live_context.to_summary_dict(),
            "constraints_count": len(self.constraints),
            "scif_decisions": [d.to_dict() for d in self.decisions],
            # Google Places provider stats
            "place_provider": self.provider_trace.get("place_provider", "unknown"),
            "candidate_stats": self.provider_trace.get("candidate_stats", {}),
            "rejected_slots": self.provider_trace.get("rejected_slots", []),
        }
