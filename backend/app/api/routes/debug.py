"""
Debug route for SmartTrip AI SCIF Layer.

Provides development-only endpoints to inspect live cognitive context
without triggering a full itinerary generation.

IMPORTANT: This router is ONLY registered when ENVIRONMENT != "production".
           See app/api/router.py for the conditional include.

Endpoints:
    GET /api/v1/debug/cognitive-context
        Returns live context snapshot for a given destination + date range.
        Shows: memory status, weather, opening hours availability,
               SCIF decisions (pre-generation pass).

Never exposes: API keys, raw user PII, provider secrets.
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, Query
from typing import Annotated

from app.api.deps import CurrentUser, get_live_context_engine_dep
from app.cognitive.live_context_engine import LiveContextEngine
from app.integrations.navigation_service import NavigationService, get_navigation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug", tags=["Debug (dev only)"])


@router.get("/cognitive-context")
async def get_cognitive_context_trace(
    destination: str = Query(..., description="Destination city/place"),
    start_date: date = Query(..., description="Trip start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Trip end date (YYYY-MM-DD)"),
    current_user: CurrentUser = None,
    live_context_engine: Annotated[LiveContextEngine, Depends(get_live_context_engine_dep)] = None,
    navigation_service: NavigationService = Depends(get_navigation_service),
) -> dict:
    """
    Development-only: inspect the live cognitive context that would be built
    for a given destination and travel date range.

    Returns:
        - Weather forecast per travel day (Open-Meteo)
        - Available vs. unavailable live sources
        - SCIF planning constraints derived from weather
        - current_datetime (IST)

    This does NOT trigger Qwen, Geoapify, or Firestore operations.
    """
    # Geocode destination
    lat: float | None = None
    lon: float | None = None
    geocode_result = None
    try:
        geocode_result = await navigation_service.geocode(destination)
        if geocode_result:
            lat = geocode_result["lat"]
            lon = geocode_result["lon"]
    except Exception as exc:
        logger.warning("debug/cognitive-context geocode failed for %r: %s", destination, exc)

    if lat is None:
        return {
            "destination": destination,
            "geocode_status": "failed",
            "live_context": None,
            "error": "Could not geocode destination — geocoding service may be unavailable.",
        }

    # Build live context
    live_context = await live_context_engine.build_live_context(
        destination=destination,
        lat=lat,
        lon=lon,
        start_date=start_date,
        end_date=end_date,
    )

    # Derive constraints
    constraints = live_context_engine.derive_constraints(
        live_context, start_date, end_date
    )

    return {
        "destination": destination,
        "geocode": {"lat": lat, "lon": lon},
        "geocode_source": geocode_result.get("source", "osrm") if geocode_result else None,
        "live_context": live_context.to_summary_dict(),
        "scif_constraints": constraints,
        "data_sources": {
            "weather": "open-meteo (free, no key required)",
            "opening_hours": "geoapify (from place enrichment — not available at this endpoint)",
            "traffic": "unavailable (OSRM is static routing)",
            "events": "unavailable (no events API integrated)",
        },
        "note": "This endpoint is dev-only. Not available in production.",
    }
