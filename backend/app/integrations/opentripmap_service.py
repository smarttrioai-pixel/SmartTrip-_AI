"""
OpenTripMap POI Integration Service for SmartTrip AI.
Fetches point-of-interest data, category matching, rating, and location metadata.

Phase 3B: removed a hardcoded public API key that was committed directly
in source and used as a silent fallback whenever OPENTRIPMAP_API_KEY was
unset. Also removed the 3 fabricated fallback POIs ("Historical City
Landmark," etc.) previously returned on any failure — an empty list is
the honest response when real POI data can't be fetched, not a set of
fake attractions indistinguishable from real ones.
"""
from __future__ import annotations

import logging
from typing import Any
import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

class OpenTripMapService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._poi_cache: dict[str, list[dict[str, Any]]] = {}

    async def search_pois(
        self, lat: float, lon: float, radius_m: int = 5000, category: str = "interesting_places"
    ) -> list[dict[str, Any]]:
        cache_key = f"{round(lat,2)},{round(lon,2)},{category}"
        if cache_key in self._poi_cache:
            return self._poi_cache[cache_key]

        api_key = self.settings.OPENTRIPMAP_API_KEY
        if not api_key:
            logger.warning("OPENTRIPMAP_API_KEY is not set — cannot fetch real POI data")
            return []

        try:
            url = f"https://api.opentripmap.com/0.1/en/places/radius?radius={radius_m}&lon={lon}&lat={lat}&kinds={category}&format=json&apikey={api_key}"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    pois = []
                    for item in data[:15]:
                        pois.append({
                            "xid": item.get("xid", ""),
                            "name": item.get("name", "Local Attraction"),
                            "rate": item.get("rate", 3),
                            "kinds": item.get("kinds", category).split(","),
                            "lat": item.get("point", {}).get("lat", lat),
                            "lon": item.get("point", {}).get("lon", lon),
                            "popularity_score": round(min(1.0, item.get("rate", 3) / 7.0), 2),
                        })
                    self._poi_cache[cache_key] = pois
                    return pois
        except Exception as e:
            logger.warning("OpenTripMap POI fetch failed: %s", e)

        return []  # honest empty result — no fabricated fallback places

_opentripmap_service = OpenTripMapService()

def get_opentripmap_service() -> OpenTripMapService:
    return _opentripmap_service
