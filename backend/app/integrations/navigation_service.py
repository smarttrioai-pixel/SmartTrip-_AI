"""
Navigation & Routing Service for SmartTrip AI.

Geocoding via OpenStreetMap Nominatim (was already a real API call).
Routing now calls OSRM's public demo routing server for a real
road-following route, distance, ETA, and turn-by-turn steps. Previously,
calculate_route() never called any routing API at all despite its
docstring naming OpenRouteService/OSRM/OpenStreetMap - it fabricated
straight-line haversine distance and 3 generic templated instruction
strings regardless of the actual path. geocode()'s failure path also
returned a hardcoded Paris-coordinate fallback rather than a real "not
found" signal - silently mislabeling any unrecognized place as Paris.

Note on OSRM's public demo server: rate-limited, intended for light/demo
use rather than production traffic at scale - documented here as a known
constraint. Upgrade path is a self-hosted OSRM instance or a commercial
provider.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

OSRM_PROFILE_MAP = {"walking": "foot", "cycling": "bike", "driving": "car"}
OSRM_BASE_URL = "https://router.project-osrm.org/route/v1"


class NavigationService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._geocode_cache: dict[str, dict[str, Any]] = {}

    async def geocode(self, query: str) -> dict[str, Any] | None:
        """
        Geocode a place name via OpenStreetMap Nominatim.
        Returns None on failure or no match - NOT a fallback location.
        Silently defaulting an unrecognized place to a real city's
        coordinates would put it on the map/in weather scoring as if it
        were a valid result, which is worse than honestly reporting
        "not found."
        """
        if query in self._geocode_cache:
            return self._geocode_cache[query]

        try:
            url = f"https://nominatim.openstreetmap.org/search?format=json&q={query}&limit=1"
            headers = {"User-Agent": "SmartTripAI/2.0"}
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200 and resp.json():
                    item = resp.json()[0]
                    result = {
                        "lat": float(item["lat"]),
                        "lon": float(item["lon"]),
                        "display_name": item.get("display_name", query),
                    }
                    self._geocode_cache[query] = result
                    return result
        except Exception as e:
            logger.warning("Geocoding failed for '%s': %s", query, e)

        return None

    async def calculate_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        mode: str = "driving",
    ) -> dict[str, Any] | None:
        """
        Real routing via OSRM's public demo server. Returns None on
        failure - callers must surface "route unavailable," never
        substitute a fabricated straight-line path.
        """
        profile = OSRM_PROFILE_MAP.get(mode.lower(), "car")
        url = (
            f"{OSRM_BASE_URL}/{profile}/{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
            f"?overview=full&geometries=geojson&steps=true"
        )

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning(
                "OSRM routing failed (%s,%s -> %s,%s): %s", origin_lat, origin_lon, dest_lat, dest_lon, e
            )
            return None

        if data.get("code") != "Ok" or not data.get("routes"):
            logger.warning("OSRM returned no route: %s", data.get("code"))
            return None

        route = data["routes"][0]
        steps: list[dict[str, Any]] = []
        for leg in route.get("legs", []):
            for step in leg.get("steps", []):
                maneuver = step.get("maneuver", {})
                steps.append(
                    {
                        "instruction": self._format_instruction(maneuver, step.get("name", "")),
                        "distance_km": round(step.get("distance", 0) / 1000, 2),
                    }
                )

        return {
            "origin": {"lat": origin_lat, "lon": origin_lon},
            "destination": {"lat": dest_lat, "lon": dest_lon},
            "mode": mode,
            "distance_km": round(route["distance"] / 1000, 2),
            "duration_minutes": round(route["duration"] / 60),
            "eta_formatted": f"{round(route['duration'] / 60)} mins",
            "coordinates": route.get("geometry", {}).get("coordinates", []),
            "steps": steps,
        }

    @staticmethod
    def _format_instruction(maneuver: dict, road_name: str) -> str:
        maneuver_type = maneuver.get("type", "continue")
        modifier = maneuver.get("modifier", "")
        road = f" onto {road_name}" if road_name else ""
        if maneuver_type == "depart":
            return f"Head {modifier or 'out'}{road}"
        if maneuver_type == "arrive":
            return "Arrive at destination"
        if modifier:
            return f"Turn {modifier}{road}"
        return f"Continue{road}"


_navigation_service = NavigationService()


def get_navigation_service() -> NavigationService:
    return _navigation_service
