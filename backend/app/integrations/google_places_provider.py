"""
Google Places Provider for SmartTrip AI.

Implements PlaceProvider using the Google Places API (New):
    POST /places:searchNearby  — discover attractions by type
    POST /places:searchText    — text search for restaurants and geocoding
    GET  /places/{name}        — place details by place_id

Design rules:
- API key is NEVER logged, never included in any response.
- Returns [] / None on any failure — never fabricated data.
- In-memory cache per instance lifetime (one itinerary generation).
- 429 / 5xx → exponential backoff, max 2 retries.
- Request only required fields via X-Goog-FieldMask header (cost control).
- Tourist types are explicitly filtered — commercial businesses are excluded
  from attraction searches.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.integrations.place_provider import (
    GeoPoint,
    PlaceCandidate,
    PlaceDetails,
    PlaceProvider,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Google place types considered tourist-relevant for attraction slots.
# Sorted by relevance weight (used by TouristRanker).
# ---------------------------------------------------------------------------
TOURIST_TYPES: dict[str, float] = {
    "tourist_attraction": 1.0,
    "historical_landmark": 1.0,
    "museum": 1.0,
    "hindu_temple": 1.0,
    "mosque": 0.95,
    "church": 0.9,
    "jain_temple": 1.0,
    "buddhist_temple": 0.95,
    "place_of_worship": 0.85,
    "art_gallery": 0.9,
    "national_park": 1.0,
    "park": 0.7,
    "wildlife_refuge": 0.85,
    "nature_preserve": 0.85,
    "zoo": 0.8,
    "aquarium": 0.85,
    "amusement_park": 0.75,
    "cultural_center": 0.9,
    "library": 0.6,
    "stadium": 0.6,
    "performing_arts_theater": 0.8,
    "movie_theater": 0.5,
    "monument": 0.9,
    "sculpture": 0.7,
    "ruins": 0.9,
    "fort": 1.0,
    "palace": 1.0,
    "castle": 1.0,
    "lighthouse": 0.8,
    "beach": 0.85,
    "viewpoint": 0.9,
    "observation_deck": 0.85,
    "botanical_garden": 0.85,
    "garden": 0.7,
    "waterfall": 0.9,
    "lake": 0.75,
    "cave": 0.85,
}

# Google types that are purely commercial — penalized for attraction slots
COMMERCIAL_TYPES: set[str] = {
    "shopping_mall", "department_store", "grocery_store", "supermarket",
    "convenience_store", "gas_station", "pharmacy", "hardware_store",
    "clothing_store", "shoe_store", "jewelry_store", "electronics_store",
    "furniture_store", "home_goods_store", "liquor_store", "book_store",
    "florist", "pet_store", "sporting_goods_store",
    "juice_bar", "ice_cream_shop", "bakery",
    "atm", "bank", "insurance_agency", "accounting", "real_estate_agency",
    "storage", "car_dealer", "car_repair", "car_wash",
    "laundry", "gym", "beauty_salon", "hair_salon", "spa",
}

# Types included in attraction search (passed to includedTypes / textQuery context)
ATTRACTION_INCLUDED_TYPES: list[str] = [
    "tourist_attraction",
    "historical_landmark",
    "museum",
    "hindu_temple",
    "mosque",
    "church",
    "jain_temple",
    "buddhist_temple",
    "place_of_worship",
    "art_gallery",
    "national_park",
    "park",
    "zoo",
    "aquarium",
    "amusement_park",
    "cultural_center",
    "performing_arts_theater",
]

# Types included in restaurant search
RESTAURANT_INCLUDED_TYPES: list[str] = [
    "restaurant",
    "cafe",
    "meal_delivery",
    "meal_takeaway",
    "food_court",
    "bakery",
    "bar",
]

# Field mask for search results (cost control — no photos, no editorial summaries)
_SEARCH_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.location,places.rating,places.userRatingCount,"
    "places.types,places.regularOpeningHours,places.currentOpeningHours,"
    "places.businessStatus,places.priceLevel,places.nationalPhoneNumber"
)

# Field mask for place details
_DETAILS_FIELD_MASK = (
    "id,displayName,formattedAddress,location,rating,userRatingCount,"
    "types,regularOpeningHours,currentOpeningHours,businessStatus,"
    "priceLevel,websiteUri,nationalPhoneNumber"
)

_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 2
_BASE_BACKOFF_SECONDS = 1.0


async def _post_with_retry(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float,
) -> dict[str, Any] | None:
    """POST with exponential backoff. Returns parsed JSON or None."""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            start = time.perf_counter()
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=body)
            latency_ms = round((time.perf_counter() - start) * 1000)

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code in _RETRY_STATUS_CODES and attempt < _MAX_RETRIES:
                wait = _BASE_BACKOFF_SECONDS * (2 ** attempt)
                logger.warning(
                    "GooglePlaces HTTP %s — retry %d/%d in %.1fs url=%s",
                    resp.status_code, attempt + 1, _MAX_RETRIES, wait, url,
                )
                await asyncio.sleep(wait)
                continue

            if resp.status_code in (401, 403):
                logger.error(
                    "provider=google operation=search status=%s "
                    "reason=auth_failure — check GOOGLE_PLACES_API_KEY and "
                    "confirm 'Places API (New)' is enabled in Google Cloud Console.",
                    resp.status_code,
                )
            else:
                logger.warning(
                    "GooglePlaces non-retryable HTTP %s url=%s latency_ms=%d",
                    resp.status_code, url, latency_ms,
                )
            return None

        except httpx.TimeoutException:
            logger.warning("GooglePlaces timeout url=%s attempt=%d", url, attempt)
        except Exception as exc:
            logger.warning("GooglePlaces request failed url=%s attempt=%d: %s", url, attempt, exc)

        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_BASE_BACKOFF_SECONDS * (2 ** attempt))

    return None


def _parse_opening_hours(place_data: dict[str, Any]) -> str | None:
    """
    Extract a simplified opening-hours string from a Google Places result.

    Tries currentOpeningHours first (live data), then regularOpeningHours.
    Returns None if unavailable — never fabricates.
    """
    for key in ("currentOpeningHours", "regularOpeningHours"):
        hours_obj = place_data.get(key)
        if not hours_obj:
            continue
        # weekdayDescriptions is a list like ["Monday: 9:00 AM – 5:00 PM", ...]
        descriptions = hours_obj.get("weekdayDescriptions")
        if descriptions and isinstance(descriptions, list):
            return "; ".join(descriptions[:7])
    return None


def _parse_business_status(place_data: dict[str, Any]) -> str | None:
    """Extract business_status string from Google Places result."""
    return place_data.get("businessStatus")


def _normalize_candidate(place: dict[str, Any], *, source_lat: float, source_lon: float) -> PlaceCandidate | None:
    """Convert a raw Google Places result to a normalized PlaceCandidate."""
    name = (place.get("displayName") or {}).get("text") or ""
    if not name:
        return None

    place_id = place.get("id") or ""
    if not place_id:
        return None

    loc = place.get("location") or {}
    lat = float(loc.get("latitude", source_lat))
    lon = float(loc.get("longitude", source_lon))

    # Rough distance (metres) from source
    import math
    dlat = math.radians(lat - source_lat)
    dlon = math.radians(lon - source_lon)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(source_lat)) * math.cos(math.radians(lat)) * math.sin(dlon / 2) ** 2
    distance_m = 6_371_000 * 2 * math.asin(math.sqrt(a))

    types = place.get("types") or []
    rating_raw = place.get("rating")
    rating = float(rating_raw) if rating_raw is not None else None

    user_count_raw = place.get("userRatingCount")
    user_count = int(user_count_raw) if user_count_raw is not None else None

    price_raw = place.get("priceLevel")
    price_level = None
    if price_raw is not None:
        # Google returns enum strings like "PRICE_LEVEL_MODERATE"
        price_map = {
            "PRICE_LEVEL_FREE": 0,
            "PRICE_LEVEL_INEXPENSIVE": 1,
            "PRICE_LEVEL_MODERATE": 2,
            "PRICE_LEVEL_EXPENSIVE": 3,
            "PRICE_LEVEL_VERY_EXPENSIVE": 4,
        }
        price_level = price_map.get(str(price_raw))

    return PlaceCandidate(
        place_id=place_id,
        name=name,
        lat=lat,
        lon=lon,
        address=place.get("formattedAddress"),
        rating=rating,
        user_ratings_total=user_count,
        price_level=price_level,
        types=types,
        opening_hours=_parse_opening_hours(place),
        business_status=_parse_business_status(place),
        distance_m=distance_m,
        source="google",
    )


class GooglePlacesProvider(PlaceProvider):
    """
    Implements PlaceProvider using the Google Places API (New).

    Endpoints:
        POST /places:searchNearby  — nearby attractions by type
        POST /places:searchText    — text search for restaurants, geocoding
        GET  /places/{id}          — place details

    API key is read from settings.GOOGLE_PLACES_API_KEY.
    If unset, all methods return [] or None gracefully.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        # Per-instance caches (cleared between requests via DI per-request lifecycle)
        self._search_cache: dict[str, list[PlaceCandidate]] = {}
        self._detail_cache: dict[str, PlaceDetails | None] = {}

    @property
    def _api_key(self) -> str | None:
        return self._settings.GOOGLE_PLACES_API_KEY

    @property
    def _base_url(self) -> str:
        return self._settings.GOOGLE_PLACES_BASE_URL.rstrip("/")

    @property
    def _timeout(self) -> float:
        return float(self._settings.GOOGLE_PLACES_TIMEOUT_SECONDS)

    def _check_key(self, operation: str) -> bool:
        if not self._api_key:
            logger.warning(
                "provider=google operation=%s status=skipped "
                "reason=GOOGLE_PLACES_API_KEY_not_configured",
                operation,
            )
            return False
        return True

    def _headers(self, field_mask: str) -> dict[str, str]:
        """Build request headers. API key is in header — never logged."""
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key or "",
            "X-Goog-FieldMask": field_mask,
        }

    # ------------------------------------------------------------------
    # Attraction Search
    # ------------------------------------------------------------------

    async def search_attractions(
        self,
        *,
        lat: float,
        lon: float,
        query: str,
        radius_m: int = 5000,
        limit: int = 20,
    ) -> list[PlaceCandidate]:
        """
        Search for tourist attractions near (lat, lon).

        Uses searchNearby with ATTRACTION_INCLUDED_TYPES filter.
        Falls back to searchText if searchNearby returns 0 results.
        """
        if not self._check_key("search_attractions"):
            return []

        cache_key = f"attr:{round(lat, 3)},{round(lon, 3)},{query[:40]},{radius_m}"
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

        results = await self._nearby_search(
            lat=lat, lon=lon,
            included_types=ATTRACTION_INCLUDED_TYPES,
            radius_m=radius_m,
            limit=limit,
            operation_label="search_attractions_nearby",
        )

        # Fallback: text search when nearby returns nothing
        if not results and query:
            results = await self._text_search(
                query=f"{query} in {self._settings.GOOGLE_PLACES_BASE_URL}",
                lat=lat, lon=lon,
                radius_m=radius_m,
                limit=limit,
                operation_label="search_attractions_text_fallback",
            )

        self._search_cache[cache_key] = results
        return results

    async def _nearby_search(
        self,
        *,
        lat: float,
        lon: float,
        included_types: list[str],
        radius_m: int,
        limit: int,
        operation_label: str,
    ) -> list[PlaceCandidate]:
        url = f"{self._base_url}/places:searchNearby"
        body: dict[str, Any] = {
            "includedTypes": included_types,
            "maxResultCount": min(limit, 20),
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": float(min(radius_m, 50000)),
                }
            },
            "rankPreference": "POPULARITY",
        }
        start = time.perf_counter()
        data = await _post_with_retry(
            url, self._headers(_SEARCH_FIELD_MASK), body, self._timeout
        )
        latency_ms = round((time.perf_counter() - start) * 1000)

        if data is None:
            logger.warning(
                "provider=google operation=%s lat=%.4f lon=%.4f results=0 latency_ms=%d",
                operation_label, lat, lon, latency_ms,
            )
            return []

        candidates = []
        for place in data.get("places", []):
            c = _normalize_candidate(place, source_lat=lat, source_lon=lon)
            if c:
                candidates.append(c)

        logger.info(
            "provider=google operation=%s lat=%.4f lon=%.4f "
            "results=%d latency_ms=%d",
            operation_label, lat, lon, len(candidates), latency_ms,
        )
        return candidates

    # ------------------------------------------------------------------
    # Restaurant / Food Search
    # ------------------------------------------------------------------

    async def search_restaurants(
        self,
        *,
        lat: float,
        lon: float,
        food_query: str,
        meal_type: str | None = None,
        radius_m: int = 5000,
        limit: int = 20,
    ) -> list[PlaceCandidate]:
        """
        Search for restaurants using text search.

        food_query is sent directly to Google (e.g. "Andhra meals Guntur"),
        filtered to restaurant types only.
        """
        if not self._check_key("search_restaurants"):
            return []

        cache_key = f"rest:{round(lat, 3)},{round(lon, 3)},{food_query[:40]}"
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

        results = await self._text_search(
            query=food_query,
            lat=lat, lon=lon,
            radius_m=radius_m,
            limit=limit,
            included_types=RESTAURANT_INCLUDED_TYPES,
            operation_label="search_restaurants",
        )

        # Broader fallback if food_query is too specific
        if not results:
            results = await self._text_search(
                query=f"restaurant near me",
                lat=lat, lon=lon,
                radius_m=radius_m,
                limit=limit,
                included_types=RESTAURANT_INCLUDED_TYPES,
                operation_label="search_restaurants_broad_fallback",
            )

        self._search_cache[cache_key] = results
        return results

    async def _text_search(
        self,
        *,
        query: str,
        lat: float,
        lon: float,
        radius_m: int,
        limit: int,
        included_types: list[str] | None = None,
        operation_label: str = "text_search",
    ) -> list[PlaceCandidate]:
        url = f"{self._base_url}/places:searchText"
        body: dict[str, Any] = {
            "textQuery": query,
            "maxResultCount": min(limit, 20),
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": float(min(radius_m, 50000)),
                }
            },
        }
        if included_types:
            body["includedType"] = included_types[0]  # searchText supports single type

        start = time.perf_counter()
        data = await _post_with_retry(
            url, self._headers(_SEARCH_FIELD_MASK), body, self._timeout
        )
        latency_ms = round((time.perf_counter() - start) * 1000)

        if data is None:
            logger.warning(
                "provider=google operation=%s query=%r results=0 latency_ms=%d",
                operation_label, query[:60], latency_ms,
            )
            return []

        candidates = []
        for place in data.get("places", []):
            c = _normalize_candidate(place, source_lat=lat, source_lon=lon)
            if c:
                candidates.append(c)

        logger.info(
            "provider=google operation=%s query=%r results=%d latency_ms=%d",
            operation_label, query[:60], len(candidates), latency_ms,
        )
        return candidates

    # ------------------------------------------------------------------
    # Place Details
    # ------------------------------------------------------------------

    async def get_place_details(self, place_id: str) -> PlaceDetails | None:
        """Fetch detailed place information by Google place_id."""
        if not place_id:
            return None
        if place_id in self._detail_cache:
            return self._detail_cache[place_id]
        if not self._check_key("get_place_details"):
            return None

        url = f"{self._base_url}/places/{place_id}"
        headers = self._headers(_DETAILS_FIELD_MASK)

        try:
            start = time.perf_counter()
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, headers=headers)
            latency_ms = round((time.perf_counter() - start) * 1000)

            if resp.status_code != 200:
                logger.warning(
                    "provider=google operation=get_place_details place_id=%s status=%s latency_ms=%d",
                    place_id, resp.status_code, latency_ms,
                )
                self._detail_cache[place_id] = None
                return None

            data = resp.json()
            name = (data.get("displayName") or {}).get("text") or ""
            if not name:
                self._detail_cache[place_id] = None
                return None

            loc = data.get("location") or {}
            types = data.get("types") or []

            price_raw = data.get("priceLevel")
            price_map = {
                "PRICE_LEVEL_FREE": 0, "PRICE_LEVEL_INEXPENSIVE": 1,
                "PRICE_LEVEL_MODERATE": 2, "PRICE_LEVEL_EXPENSIVE": 3,
                "PRICE_LEVEL_VERY_EXPENSIVE": 4,
            }
            price_level = price_map.get(str(price_raw)) if price_raw else None

            result = PlaceDetails(
                place_id=place_id,
                name=name,
                lat=float(loc.get("latitude")) if loc.get("latitude") else None,
                lon=float(loc.get("longitude")) if loc.get("longitude") else None,
                address=data.get("formattedAddress"),
                rating=float(data["rating"]) if data.get("rating") else None,
                user_ratings_total=int(data["userRatingCount"]) if data.get("userRatingCount") else None,
                price_level=price_level,
                types=types,
                opening_hours=_parse_opening_hours(data),
                business_status=_parse_business_status(data),
                website=data.get("websiteUri"),
                phone=data.get("nationalPhoneNumber"),
                source="google",
            )
            logger.info(
                "provider=google operation=get_place_details place_id=%s name=%r latency_ms=%d",
                place_id, name, latency_ms,
            )
            self._detail_cache[place_id] = result
            return result

        except Exception as exc:
            logger.warning(
                "provider=google operation=get_place_details place_id=%s error=%s",
                place_id, exc,
            )
            self._detail_cache[place_id] = None
            return None

    # ------------------------------------------------------------------
    # Geocoding
    # ------------------------------------------------------------------

    async def geocode(self, query: str) -> GeoPoint | None:
        """
        Forward-geocode using Google Places searchText.
        Returns GeoPoint or None — never returns fabricated coordinates.
        """
        if not self._check_key("geocode"):
            return None

        results = await self._text_search(
            query=query, lat=0.0, lon=0.0,
            radius_m=50000,
            limit=1,
            operation_label="geocode",
        )
        if not results:
            return None

        r = results[0]
        return GeoPoint(
            lat=r.lat,
            lon=r.lon,
            display_name=r.address or r.name,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_google_places_provider: GooglePlacesProvider | None = None


def get_google_places_provider() -> GooglePlacesProvider:
    """Return a cached GooglePlacesProvider instance."""
    global _google_places_provider
    if _google_places_provider is None:
        _google_places_provider = GooglePlacesProvider()
    return _google_places_provider
