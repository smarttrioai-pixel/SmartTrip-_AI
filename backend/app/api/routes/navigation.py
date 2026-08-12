"""
Navigation & Map API Router for SmartTrip AI.
Endpoints for geocoding, route calculation, ETA, and nearby attraction lookup.

Phase 3B: geocode() and calculate_route() now return None on failure
instead of a fabricated fallback/route (see navigation_service.py) — this
router now surfaces that honestly as 404/503 instead of returning null in
a 200 response.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser
from app.integrations.navigation_service import NavigationService, get_navigation_service
from app.integrations.opentripmap_service import OpenTripMapService, get_opentripmap_service

router = APIRouter(prefix="/navigation", tags=["Navigation"])

@router.get("/geocode", summary="Geocode place name to coordinates")
async def geocode_place(
    current_user: CurrentUser,
    q: str = Query(..., description="Place or city name to geocode"),
    nav_service: NavigationService = Depends(get_navigation_service),
) -> dict[str, Any]:
    result = await nav_service.geocode(q)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Could not geocode '{q}'")
    return result

@router.get("/route", summary="Calculate route between two points")
async def get_route(
    current_user: CurrentUser,
    origin_lat: float = Query(...),
    origin_lon: float = Query(...),
    dest_lat: float = Query(...),
    dest_lon: float = Query(...),
    mode: str = Query("driving", description="Mode of travel: walking, cycling, driving"),
    nav_service: NavigationService = Depends(get_navigation_service),
) -> dict[str, Any]:
    result = await nav_service.calculate_route(origin_lat, origin_lon, dest_lat, dest_lon, mode=mode)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Routing service unavailable for this request"
        )
    return result

@router.get("/nearby", summary="Fetch nearby attractions using POI service")
async def get_nearby_attractions(
    current_user: CurrentUser,
    lat: float = Query(...),
    lon: float = Query(...),
    radius_m: int = Query(5000),
    poi_service: OpenTripMapService = Depends(get_opentripmap_service),
) -> list[dict[str, Any]]:
    return await poi_service.search_pois(lat, lon, radius_m=radius_m)
