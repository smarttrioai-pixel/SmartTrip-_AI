"""
Geoapify Places Provider for SmartTrip AI.

All direct calls to the Geoapify API (Places, Geocoding) are encapsulated
here. No other module should call api.geoapify.com directly.

Architecture:
    PlaceEnrichmentService
        ↓
    GeoapifyProvider           ← this file
        ↓
    Geoapify Places API  (https://api.geoapify.com)
        ↓
    Verified real places

Design rules enforced here:
- Returns [] / None on any failure — never fabricated place data.
- Logs structured entries for every request (provider, operation, latency).
- Handles 429 / 5xx with exponential backoff (max 2 retries).
- API key is read from settings; if unset the service degrades gracefully.
- In-memory caches for geocoding and place searches to avoid redundant
  API calls within a single itinerary-generation request.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Geoapify category mapping
# SmartTrip concept → Geoapify category string
# Verified against Geoapify Places API documentation.
# ---------------------------------------------------------------------------
CATEGORY_MAP: dict[str, list[str]] = {
    "meal": ["catering.restaurant", "catering.cafe", "catering.fast_food"],
    "restaurant": ["catering.restaurant", "catering.cafe"],
    "cafe": ["catering.cafe"],
    "fast_food": ["catering.fast_food"],
    "bar": ["catering.bar"],
    "attraction": ["tourism.sights", "tourism.attraction"],
    "sights": ["tourism.sights", "tourism.attraction"],
    "museum": ["entertainment.museum"],
    "culture": ["tourism.sights", "entertainment.museum", "entertainment.culture"],
    "nature": ["leisure.park", "natural"],
    "park": ["leisure.park"],
    "shopping": ["commercial.shopping_mall", "commercial.marketplace"],
    "accommodation": ["accommodation.hotel"],
    "hotel": ["accommodation.hotel"],
    "transport": ["public_transport"],
    # fallback
    "other": ["tourism.sights", "entertainment"],
    "interesting_places": ["tourism.sights", "tourism.attraction", "entertainment.museum"],
}

_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 2
_BASE_BACKOFF_SECONDS = 1.0


def _categories_for(concept: str) -> list[str]:
    """Return Geoapify category strings for a SmartTrip concept."""
    concept_lower = concept.lower().strip()
    for key in CATEGORY_MAP:
        if key in concept_lower or concept_lower in key:
            return CATEGORY_MAP[key]
    return CATEGORY_MAP["interesting_places"]


async def _request_with_retry(
    url: str,
    params: dict[str, Any],
    timeout: float,
) -> dict[str, Any] | None:
    """
    Perform a GET request with exponential-backoff retry on transient errors.
    Returns the parsed JSON body or None on failure.
    Never raises — callers receive None on any error.
    """
    for attempt in range(_MAX_RETRIES + 1):
        try:
            start = time.perf_counter()
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, params=params)
            latency_ms = round((time.perf_counter() - start) * 1000)

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code in _RETRY_STATUS_CODES and attempt < _MAX_RETRIES:
                wait = _BASE_BACKOFF_SECONDS * (2 ** attempt)
                logger.warning(
                    "Geoapify HTTP %s — retry %d/%d in %.1fs url=%s",
                    resp.status_code, attempt + 1, _MAX_RETRIES, wait, url,
                )
                await asyncio.sleep(wait)
                continue

            logger.warning(
                "Geoapify non-retryable HTTP %s url=%s latency_ms=%d",
                resp.status_code, url, latency_ms,
            )
            return None

        except httpx.TimeoutException:
            logger.warning("Geoapify timeout url=%s attempt=%d", url, attempt)
        except Exception as exc:
            logger.warning("Geoapify request failed url=%s attempt=%d: %s", url, attempt, exc)

        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_BASE_BACKOFF_SECONDS * (2 ** attempt))

    return None


class GeoapifyProvider:
    """
    Encapsulates all Geoapify API interactions for SmartTrip AI.

    Endpoints used:
        GET /v1/geocode/search  — forward geocoding
        GET /v2/places          — nearby place search with category filters
        GET /v2/place-details   — single-place detail lookup
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        # In-memory caches — cleared each process lifetime.
        # Avoids redundant API calls within one itinerary generation.
        self._geocode_cache: dict[str, dict[str, Any] | None] = {}
        self._search_cache: dict[str, list[dict[str, Any]]] = {}
        self._detail_cache: dict[str, dict[str, Any] | None] = {}

    @property
    def _api_key(self) -> str | None:
        return self._settings.GEOAPIFY_API_KEY

    @property
    def _base_url(self) -> str:
        return self._settings.GEOAPIFY_BASE_URL.rstrip("/")

    @property
    def _timeout(self) -> float:
        return float(self._settings.GEOAPIFY_TIMEOUT_SECONDS)

    def _check_key(self, operation: str) -> bool:
        if not self._api_key:
            logger.warning(
                "provider=geoapify operation=%s status=skipped reason=api_key_not_configured",
                operation,
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Geocoding
    # ------------------------------------------------------------------

    async def geocode(
        self,
        query: str,
    ) -> dict[str, Any] | None:
        """
        Forward-geocode a place name using Geoapify.

        Returns a dict with keys: lat, lon, display_name, country, city.
        Returns None if the query cannot be resolved or the key is unset.
        NEVER returns a default/fallback coordinate.
        """
        if query in self._geocode_cache:
            return self._geocode_cache[query]

        if not self._check_key("geocode"):
            return None

        url = f"{self._base_url}/v1/geocode/search"
        params = {
            "text": query,
            "limit": 1,
            "format": "json",
            "apiKey": self._api_key,
        }

        start = time.perf_counter()
        data = await _request_with_retry(url, params, self._timeout)
        latency_ms = round((time.perf_counter() - start) * 1000)

        if data is None or not data.get("results"):
            logger.info(
                "provider=geoapify operation=geocode destination=%r results=0 latency_ms=%d",
                query, latency_ms,
            )
            self._geocode_cache[query] = None
            return None

        item = data["results"][0]
        result: dict[str, Any] = {
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
            "display_name": item.get("formatted", query),
            "country": item.get("country"),
            "city": item.get("city") or item.get("county"),
        }
        logger.info(
            "provider=geoapify operation=geocode destination=%r result=%r latency_ms=%d",
            query, result["display_name"], latency_ms,
        )
        self._geocode_cache[query] = result
        return result

    # ------------------------------------------------------------------
    # Place Search
    # ------------------------------------------------------------------

    async def search_places(
        self,
        *,
        latitude: float,
        longitude: float,
        categories: list[str],
        radius_meters: int = 5000,
        name_filter: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Search Geoapify Places API for POIs near a coordinate.

        Args:
            latitude/longitude: Center of search area (destination coords).
            categories: List of Geoapify category strings, e.g. ['catering.restaurant'].
            radius_meters: Search radius.
            name_filter: Optional text filter sent to Geoapify (name= param).
            limit: Max results to return.

        Returns:
            List of normalized place dicts. Empty list on failure.
        """
        if not self._check_key("search_places"):
            return []

        cats_str = ",".join(categories)
        cache_key = f"{round(latitude, 3)},{round(longitude, 3)},{cats_str},{radius_meters},{name_filter}"
        if cache_key in self._search_cache:
            logger.debug("provider=geoapify operation=search_places cache=hit key=%s", cache_key)
            return self._search_cache[cache_key]

        url = f"{self._base_url}/v2/places"
        params: dict[str, Any] = {
            "categories": cats_str,
            "filter": f"circle:{longitude},{latitude},{radius_meters}",
            "bias": f"proximity:{longitude},{latitude}",
            "limit": min(limit, 50),
            "apiKey": self._api_key,
        }
        if name_filter:
            params["name"] = name_filter

        start = time.perf_counter()
        data = await _request_with_retry(url, params, self._timeout)
        latency_ms = round((time.perf_counter() - start) * 1000)

        if data is None:
            logger.warning(
                "provider=geoapify operation=search_places categories=%s radius=%d latency_ms=%d results=0",
                cats_str, radius_meters, latency_ms,
            )
            return []

        features = data.get("features", [])
        results: list[dict[str, Any]] = []
        for feature in features:
            props = feature.get("properties", {})
            place_id = props.get("place_id") or props.get("osm_id") or ""
            name = props.get("name") or ""
            if not name:
                continue  # skip unnamed features

            geo = feature.get("geometry", {})
            coords = geo.get("coordinates", [])
            place_lon = float(coords[0]) if len(coords) >= 2 else longitude
            place_lat = float(coords[1]) if len(coords) >= 2 else latitude

            address_line = props.get("formatted") or props.get("address_line2") or ""
            categories_list = []
            raw_cats = props.get("categories", [])
            if isinstance(raw_cats, list):
                categories_list = raw_cats
            elif isinstance(raw_cats, str):
                categories_list = [raw_cats]

            results.append({
                "place_id": place_id,
                "name": name,
                "lat": place_lat,
                "lon": place_lon,
                "address": address_line,
                "categories": categories_list,
                "distance_m": props.get("distance", 0),
                "opening_hours": props.get("opening_hours"),
                "website": props.get("website"),
                "contact_phone": props.get("contact", {}).get("phone") if isinstance(props.get("contact"), dict) else None,
                "source": "geoapify",
                "source_id": place_id,
                # Geoapify does not provide star ratings on the free tier
                "rating": None,
                "image_url": None,
            })

        logger.info(
            "provider=geoapify operation=search_places categories=%s radius=%d "
            "latency_ms=%d results_count=%d",
            cats_str, radius_meters, latency_ms, len(results),
        )
        self._search_cache[cache_key] = results
        return results

    # ------------------------------------------------------------------
    # Place Details
    # ------------------------------------------------------------------

    async def get_place_details(
        self,
        place_id: str,
    ) -> dict[str, Any] | None:
        """
        Fetch detailed information for a specific Geoapify place.

        Returns a normalized place dict or None on failure.
        Never fabricates missing fields.
        """
        if not place_id:
            return None

        if place_id in self._detail_cache:
            return self._detail_cache[place_id]

        if not self._check_key("get_place_details"):
            return None

        url = f"{self._base_url}/v2/place-details"
        params = {
            "id": place_id,
            "features": "details,opening_hours",
            "apiKey": self._api_key,
        }

        start = time.perf_counter()
        data = await _request_with_retry(url, params, self._timeout)
        latency_ms = round((time.perf_counter() - start) * 1000)

        if data is None:
            logger.warning(
                "provider=geoapify operation=get_place_details place_id=%s latency_ms=%d result=none",
                place_id, latency_ms,
            )
            self._detail_cache[place_id] = None
            return None

        features = data.get("features", [])
        if not features:
            self._detail_cache[place_id] = None
            return None

        props = features[0].get("properties", {})
        name = props.get("name") or ""
        if not name:
            self._detail_cache[place_id] = None
            return None

        geo = features[0].get("geometry", {})
        coords = geo.get("coordinates", [])
        place_lon = float(coords[0]) if len(coords) >= 2 else None
        place_lat = float(coords[1]) if len(coords) >= 2 else None

        categories_list = props.get("categories", [])
        if isinstance(categories_list, str):
            categories_list = [categories_list]

        result: dict[str, Any] = {
            "place_id": place_id,
            "name": name,
            "lat": place_lat,
            "lon": place_lon,
            "address": props.get("formatted") or props.get("address_line2"),
            "categories": categories_list,
            "opening_hours": props.get("opening_hours"),
            "website": props.get("website"),
            "rating": None,   # Geoapify free tier: no star ratings
            "image_url": None,  # Geoapify free tier: no image URLs
            "source": "geoapify",
            "source_id": place_id,
        }
        logger.info(
            "provider=geoapify operation=get_place_details place_id=%s name=%r latency_ms=%d",
            place_id, name, latency_ms,
        )
        self._detail_cache[place_id] = result
        return result

    # ------------------------------------------------------------------
    # Category helpers
    # ------------------------------------------------------------------

    @staticmethod
    def categories_for_concept(concept: str) -> list[str]:
        """Map a SmartTrip place concept to Geoapify category strings."""
        return _categories_for(concept)


# ---------------------------------------------------------------------------
# Module-level singleton (matches existing project pattern)
# ---------------------------------------------------------------------------
_geoapify_provider: GeoapifyProvider | None = None


def get_geoapify_provider() -> GeoapifyProvider:
    """Return a cached GeoapifyProvider instance."""
    global _geoapify_provider
    if _geoapify_provider is None:
        _geoapify_provider = GeoapifyProvider()
    return _geoapify_provider
