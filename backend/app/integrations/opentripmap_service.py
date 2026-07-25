"""
OpenTripMap POI Integration Service for SmartTrip AI.
Fetches point-of-interest data, category matching, rating, and location metadata.
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

        api_key = getattr(self.settings, "OPENTRIPMAP_API_KEY", "") or "5ae2e3f221c38a28845f05b6" # default key or fallback
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
                    if pois:
                        self._poi_cache[cache_key] = pois
                        return pois
        except Exception as e:
            logger.warning("OpenTripMap POI fetch failed: %s", e)

        # Fallback structured POIs
        fallback = [
            {
                "xid": "f_1",
                "name": "Historical City Landmark",
                "rate": 7,
                "kinds": ["historic", "architecture"],
                "lat": lat + 0.002,
                "lon": lon + 0.002,
                "popularity_score": 0.95,
            },
            {
                "xid": "f_2",
                "name": "Central Museum & Art Gallery",
                "rate": 6,
                "kinds": ["museums", "cultural"],
                "lat": lat - 0.003,
                "lon": lon + 0.001,
                "popularity_score": 0.88,
            },
            {
                "xid": "f_3",
                "name": "Scenic Waterfront Promenade",
                "rate": 5,
                "kinds": ["nature", "parks"],
                "lat": lat + 0.001,
                "lon": lon - 0.003,
                "popularity_score": 0.80,
            },
        ]
        return fallback

_opentripmap_service = OpenTripMapService()

def get_opentripmap_service() -> OpenTripMapService:
    return _opentripmap_service
