"""
Analytics & Intelligence Router for SmartTrip AI.

Phase 3B: every number here is now computed from the current user's real
Firestore data (TripRepository, MemoryEngine). The previous version
returned a fully hardcoded response (fixed "8 trips", "94.2% recommendation
accuracy," etc.) for any authenticated user regardless of their actual
data — Phase 3A fixed who could call this; this pass fixes what it returns.

Some metrics genuinely can't be computed yet because the underlying data
isn't tracked anywhere in the system (per-category expense breakdown, real
walking distance, carbon footprint — no Expense Tracker or GPS-tracking
module exists yet). Those are explicitly reported as unavailable rather
than fabricated. "recommendation_accuracy" is omitted entirely: it
requires ground-truth user feedback and an evaluation harness that doesn't
exist yet — a missing metric is honest, a fabricated one is not.
"""
from __future__ import annotations

import csv
import io
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from app.api.deps import CurrentUser, get_memory_engine, get_trip_repository
from app.cognitive.memory_engine import MemoryEngine
from app.repositories.trip_repository import TripRepository

router = APIRouter(prefix="/analytics", tags=["Analytics"])


async def _build_dashboard(current_user, trip_repository: TripRepository, memory_engine: MemoryEngine) -> dict[str, Any]:
    trips = await trip_repository.list_for_user(current_user.id)

    total_trips = len(trips)
    distinct_destinations = {t.destination for t in trips}
    total_days = sum(len(t.days) for t in trips)
    total_budget = sum(t.budget for t in trips)
    total_estimated_cost = sum(t.estimated_total_cost for t in trips)
    savings_rate_pct = (
        round(((total_budget - total_estimated_cost) / total_budget) * 100, 2) if total_budget > 0 else None
    )

    insights = await memory_engine.get_insights(current_user.id)

    return {
        "user_id": current_user.id,
        "travel_statistics": {
            "total_trips_planned": total_trips,
            "total_destinations": len(distinct_destinations),
            "total_days_planned": total_days,
            "distance_and_carbon_tracking": "not yet available — requires live trip GPS tracking (future phase)",
        },
        "budget_analysis": {
            "total_budget_allocated": round(total_budget, 2),
            "total_estimated_cost": round(total_estimated_cost, 2),
            "savings_rate_pct": savings_rate_pct,
            "note": "estimated_cost reflects AI-generated itinerary estimates, not tracked actual spending (Expense Tracker module not yet built)",
            "category_split": "not yet available — activities aren't currently categorized by expense type",
        },
        "declared_interests": [p.source_text for p in insights.get("preferences", [])],
        "memory_evolution": {
            "active_inferred_preferences": len(insights.get("inferred_preferences", [])),
            "behavioral_feature_weights": insights.get("feature_weights", {}),
        },
        "recommendation_accuracy": None,
        "recommendation_accuracy_note": (
            "Not measurable yet — requires an evaluation harness with ground-truth user feedback."
        ),
    }


@router.get("/dashboard", summary="Fetch real travel statistics for the current user")
async def get_analytics_dashboard(
    current_user: CurrentUser,
    trip_repository: Annotated[TripRepository, Depends(get_trip_repository)],
    memory_engine: Annotated[MemoryEngine, Depends(get_memory_engine)],
) -> dict[str, Any]:
    return await _build_dashboard(current_user, trip_repository, memory_engine)


@router.get("/export-csv", summary="Export real travel statistics as CSV")
async def export_analytics_csv(
    current_user: CurrentUser,
    trip_repository: Annotated[TripRepository, Depends(get_trip_repository)],
    memory_engine: Annotated[MemoryEngine, Depends(get_memory_engine)],
) -> Response:
    dashboard = await _build_dashboard(current_user, trip_repository, memory_engine)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Category", "Metric", "Value"])
    writer.writerow(["Travel", "Total Trips Planned", dashboard["travel_statistics"]["total_trips_planned"]])
    writer.writerow(["Travel", "Total Destinations", dashboard["travel_statistics"]["total_destinations"]])
    writer.writerow(["Travel", "Total Days Planned", dashboard["travel_statistics"]["total_days_planned"]])
    writer.writerow(["Budget", "Total Allocated", dashboard["budget_analysis"]["total_budget_allocated"]])
    writer.writerow(["Budget", "Total Estimated Cost", dashboard["budget_analysis"]["total_estimated_cost"]])
    writer.writerow(["Memory", "Active Inferred Preferences", dashboard["memory_evolution"]["active_inferred_preferences"]])

    return Response(
        content=buffer.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=SmartTrip_Analytics_{current_user.id}.csv"},
    )
