"""
Place Provider Abstraction for SmartTrip AI.

Defines the interface that all place data providers must implement.
Currently implemented by:
    GooglePlacesProvider  — primary (Google Places API New)
    GeoapifyProvider      — fallback (Geoapify Places API)

Design rules:
- All providers return normalized PlaceCandidate objects.
- Missing fields are None — never fabricated.
- Providers never raise — return [] or None on failure.
- API keys are never logged, never included in responses.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Normalized data types (provider-agnostic)
# ---------------------------------------------------------------------------

@dataclass
class GeoPoint:
    lat: float
    lon: float
    display_name: str | None = None
    country: str | None = None
    city: str | None = None


@dataclass
class PlaceCandidate:
    """
    A normalized place candidate from any provider.

    tourist_relevance is NOT set by the provider — it is set by TouristRanker
    after candidates are returned. Default 0.5 (neutral).
    """
    place_id: str
    name: str
    lat: float
    lon: float
    address: str | None = None
    # Rating on 0–5 scale (Google provides; Geoapify free tier = None)
    rating: float | None = None
    user_ratings_total: int | None = None
    # 0=free, 1=inexpensive, 2=moderate, 3=expensive, 4=very_expensive (Google scale)
    price_level: int | None = None
    # Google types list or Geoapify category strings
    types: list[str] = field(default_factory=list)
    # OSM format string ("Mo-Fr 09:00-18:00") or None
    opening_hours: str | None = None
    # "OPERATIONAL" | "CLOSED_TEMPORARILY" | "CLOSED_PERMANENTLY" | None
    business_status: str | None = None
    distance_m: float = 0.0
    source: str = "unknown"     # "google" | "geoapify"
    # Set by TouristRanker after search
    tourist_relevance: float = 0.5
    # Extra provider-specific metadata
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaceDetails:
    """Extended details fetched for a specific place_id."""
    place_id: str
    name: str
    lat: float | None
    lon: float | None
    address: str | None = None
    rating: float | None = None
    user_ratings_total: int | None = None
    price_level: int | None = None
    types: list[str] = field(default_factory=list)
    opening_hours: str | None = None
    business_status: str | None = None
    website: str | None = None
    phone: str | None = None
    source: str = "unknown"
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract Provider Interface
# ---------------------------------------------------------------------------

class PlaceProvider(ABC):
    """
    Abstract interface for all place data providers.

    All methods are async and never raise — they return empty lists or None
    on failure so the calling layer can decide to fall back or return no result.
    """

    @abstractmethod
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
        Search for tourist attractions near a coordinate.

        Args:
            lat/lon: Center of search area (destination coordinates).
            query:   Natural-language search intent (e.g. "temples in Guntur").
            radius_m: Search radius in metres.
            limit:   Maximum results to return.

        Returns:
            List of normalized PlaceCandidate objects. Empty on failure.
        """

    @abstractmethod
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
        Search for restaurants near a coordinate matching a food query.

        Args:
            lat/lon:     Center of search area.
            food_query:  Natural-language food/cuisine query (e.g. "Andhra meals").
            meal_type:   "breakfast" | "lunch" | "dinner" — used for score hints.
            radius_m:    Search radius.
            limit:       Maximum results.

        Returns:
            List of PlaceCandidate (restaurants only). Empty on failure.
        """

    @abstractmethod
    async def get_place_details(
        self,
        place_id: str,
    ) -> PlaceDetails | None:
        """
        Fetch detailed information for a specific place.

        Returns PlaceDetails or None if unavailable.
        Never fabricates missing fields.
        """

    @abstractmethod
    async def geocode(
        self,
        query: str,
    ) -> GeoPoint | None:
        """
        Forward-geocode a place name or address.

        Returns GeoPoint or None if geocoding fails.
        Never returns a fabricated coordinate.
        """
