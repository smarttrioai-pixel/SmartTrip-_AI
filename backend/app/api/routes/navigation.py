"""
Navigation & Map API Router for SmartTrip AI.
Endpoints for geocoding, route calculation, ETA, and nearby attraction lookup.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, Query, HTTPException

from app.integrations.navigation_service import NavigationService, get_navigation_service
from app.integrations.opentripmap_service import OpenTripMapService, get_opentripmap_service

router = APIRouter(prefix="/navigation", tags=["Navigation"])

@router.get("/geocode", summary="Geocode place name to coordinates")
async def geocode_place(
    q: str = Query(..., description="Place or city name to geocode"),
    nav_service: NavigationService = Depends(get_navigation_service),
) -> dict[str, Any]:
    return await nav_service.geocode(q)

@router.get("/route", summary="Calculate route between two points")
async def get_route(
    origin_lat: float = Query(...),
    origin_lon: float = Query(...),
    dest_lat: float = Query(...),
    dest_lon: float = Query(...),
    mode: str = Query("driving", description="Mode of travel: walking, cycling, driving"),
    nav_service: NavigationService = Depends(get_navigation_service),
) -> dict[str, Any]:
    return await nav_service.calculate_route(origin_lat, origin_lon, dest_lat, dest_lon, mode=mode)

@router.get("/nearby", summary="Fetch nearby attractions using POI service")
async def get_nearby_attractions(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_m: int = Query(5000),
    poi_service: OpenTripMapService = Depends(get_opentripmap_service),
) -> list[dict[str, Any]]:
    return await poi_service.search_pois(lat, lon, radius_m=radius_m)
