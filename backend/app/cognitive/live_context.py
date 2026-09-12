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

New additions (SCIF architecture improvement):
    BudgetContext        — pre-Qwen budget breakdown from BudgetAgent
    AgentOutput          — named agent contribution record for the trace
    PipelineStage        — per-stage execution record for cognitive trace
    CognitivePlanningContext — canonical single context for the full pipeline
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
# E. BudgetContext — pre-Qwen budget analysis from BudgetAgent
# -----------------------------------------------------------------------

@dataclass
class BudgetContext:
    """
    Budget breakdown produced by BudgetAgent before Qwen generates.

    All amounts are in the user's requested currency.
    tier: "budget" | "mid_range" | "luxury" — based on daily_per_person
    constraints: human-readable budget rules passed to SCIF Pass 1 and Qwen.

    Never fabricates exchange rates or per-destination cost-of-living.
    Uses simple ratios based on input budget only.
    """
    total_budget: float
    currency: str
    num_days: int
    daily_budget: float                     # total_budget / num_days
    meal_budget_per_day: float              # ~25% of daily
    activity_budget_per_day: float          # ~35% of daily
    transport_budget_per_day: float         # ~20% of daily
    accommodation_budget_per_day: float     # ~20% of daily
    tier: str                               # "budget" | "mid_range" | "luxury"
    constraints: list[str] = field(default_factory=list)
    source: str = "internal_calculation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_budget": self.total_budget,
            "currency": self.currency,
            "num_days": self.num_days,
            "daily_budget": round(self.daily_budget, 2),
            "meal_budget_per_day": round(self.meal_budget_per_day, 2),
            "activity_budget_per_day": round(self.activity_budget_per_day, 2),
            "transport_budget_per_day": round(self.transport_budget_per_day, 2),
            "accommodation_budget_per_day": round(self.accommodation_budget_per_day, 2),
            "tier": self.tier,
            "constraints": self.constraints,
            "source": self.source,
        }


# -----------------------------------------------------------------------
# F. AgentOutput — named agent contribution record
# -----------------------------------------------------------------------

@dataclass
class AgentOutput:
    """
    Records what one named planning agent contributed to the shared context.

    agent_name: one of:
        "MemoryAgent", "WeatherAgent", "NavigationAgent",
        "PlaceAgent", "RestaurantAgent", "BudgetAgent", "SafetyAgent"

    status: "ok" | "unavailable" | "error"
    data_source: e.g. "Firestore", "Open-Meteo", "Google Places", "internal"
    contribution_summary: short text for the cognitive trace (no sensitive data)
    items_returned: count of items returned (preferences, weather days, etc.)
    latency_ms: wall-clock time of this agent's execution
    """
    agent_name: str
    status: str                          # "ok" | "unavailable" | "error"
    data_source: str
    contribution_summary: str
    items_returned: int = 0
    latency_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "status": self.status,
            "data_source": self.data_source,
            "contribution": self.contribution_summary,
            "items_returned": self.items_returned,
            "latency_ms": round(self.latency_ms, 1),
            "details": self.details,
        }


# -----------------------------------------------------------------------
# G. PipelineStage — records one stage's execution for the cognitive trace
# -----------------------------------------------------------------------

@dataclass
class PipelineStage:
    """
    Records the execution of one stage in the SCIF pipeline.
    Used to produce the cognitive trace that proves the pipeline ran.

    stage_name: e.g. "MEMORY_RETRIEVAL", "WEATHER_FETCH", "SCIF_PASS_1", etc.
    component: class/service name that ran (e.g. "MemoryEngine")
    status: "ok" | "skipped" | "error"
    """
    stage_name: str
    component: str
    status: str
    summary: str
    latency_ms: float = 0.0
    items: int = 0
    data_source: str = "internal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage_name,
            "component": self.component,
            "status": self.status,
            "summary": self.summary,
            "latency_ms": round(self.latency_ms, 1),
            "items": self.items,
            "data_source": self.data_source,
        }


# -----------------------------------------------------------------------
# H. CognitivePlanningContext — canonical context for the full pipeline
# -----------------------------------------------------------------------

@dataclass
class CognitivePlanningContext:
    """
    The canonical structured object that unifies all SCIF inputs before Qwen.

    This is what SCIF Pass 1 produces and what the ContextBuilder consumes
    to build the Qwen prompt. Every field has a clear data source.

    Key design rule: keep ALL sources separate. Never merge Firestore memory
    into weather data into profile data.
    """
    # --- User request ---
    destination: str = ""
    start_date_iso: str = ""
    end_date_iso: str = ""
    num_days: int = 1
    budget: float = 0.0
    currency: str = "USD"
    travel_style: str = "balanced"
    transport: str = "any"
    interests: list[str] = field(default_factory=list)

    # --- Destination coordinates (from NavigationAgent) ---
    lat: float | None = None
    lon: float | None = None
    geocode_source: str = "unavailable"

    # --- User profile (from UserProfileEngine) ---
    food_preference: str = "no_preference"
    accommodation: str = "hotel"
    profile_interests: list[str] = field(default_factory=list)
    profile_transport: str = "any"

    # --- Persistent memory (from MemoryAgent / MemoryEngine) ---
    memory_items: int = 0
    memory_summary: str = ""
    memory_preferences: list[str] = field(default_factory=list)
    memory_feature_weights: dict[str, float] = field(default_factory=dict)

    # --- Live context (from WeatherAgent / LiveContextEngine) ---
    live_context: LiveContext = field(default_factory=LiveContext)
    weather_constraints: list[str] = field(default_factory=list)

    # --- Budget analysis (from BudgetAgent) ---
    budget_context: BudgetContext | None = None

    # --- Agent outputs (named contributions) ---
    agent_outputs: list[AgentOutput] = field(default_factory=list)

    # --- SCIF Pass 1 decisions and constraints ---
    scif_constraints: list[str] = field(default_factory=list)
    scif_decisions_pre: list[CognitiveDecision] = field(default_factory=list)

    # --- Pipeline execution trace ---
    pipeline_stages: list[PipelineStage] = field(default_factory=list)

    def add_agent_output(self, output: AgentOutput) -> None:
        self.agent_outputs.append(output)

    def add_stage(self, stage: PipelineStage) -> None:
        self.pipeline_stages.append(stage)

    def get_agent(self, name: str) -> AgentOutput | None:
        for a in self.agent_outputs:
            if a.agent_name == name:
                return a
        return None

    def all_constraints(self) -> list[str]:
        """Merged list of weather + budget + SCIF constraints for the prompt."""
        return self.weather_constraints + self.scif_constraints

    def to_trace_dict(self) -> dict[str, Any]:
        """Non-sensitive summary for the cognitive_trace API field."""
        return {
            "destination": self.destination,
            "dates": f"{self.start_date_iso} → {self.end_date_iso}",
            "num_days": self.num_days,
            "coordinates": {
                "lat": self.lat,
                "lon": self.lon,
                "source": self.geocode_source,
            },
            "memory": {
                "items_retrieved": self.memory_items,
                "source": "Firestore/memory_longterm",
                "summary": self.memory_summary[:200] if self.memory_summary else "",
            },
            "profile": {
                "food_preference": self.food_preference,
                "travel_style": self.travel_style,
                "interests": self.profile_interests,
            },
            "budget": self.budget_context.to_dict() if self.budget_context else {},
            "weather": self.live_context.to_summary_dict(),
            "weather_constraints": self.weather_constraints,
            "scif_constraints": self.scif_constraints,
            "agent_outputs": [a.to_dict() for a in self.agent_outputs],
            "pipeline_stages": [s.to_dict() for s in self.pipeline_stages],
        }


# -----------------------------------------------------------------------
# I. CognitiveContext — the full cognitive context object
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

    # G. Full pipeline context (populated when SCIFOrchestrator runs)
    planning_context: CognitivePlanningContext | None = None

    def to_trace_dict(self) -> dict[str, Any]:
        """Returns a non-sensitive summary for debug/logging."""
        base = {
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
        # Include the full planning context trace if available
        if self.planning_context is not None:
            base["scif_pipeline"] = self.planning_context.to_trace_dict()
        return base
