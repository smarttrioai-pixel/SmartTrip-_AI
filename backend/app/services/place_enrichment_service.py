"""
Place Enrichment Service for SmartTrip AI.

Bridges Gemini-generated itinerary activities (which are free-text —
title/description/location, no real place-database grounding) to real
place data. For each activity: geocode its location text, search real
OpenTripMap POIs nearby, pick the closest name match, fetch that POI's
real details (image, rating, address).

Honest by design: if geocoding fails, no POI is found, or the name match
isn't good enough, the result is None — never a fabricated card. Fields
OpenTripMap's free tier doesn't reliably provide (review count, opening
hours, ticket price) are always None with an explicit "unavailable"
reason, not invented.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from app.integrations.navigation_service import NavigationService
from app.integrations.opentripmap_service import OpenTripMapService

MIN_NAME_SIMILARITY = 0.35  # loose threshold — real POI names rarely match Gemini's activity titles exactly


def _name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


class PlaceEnrichmentService:
    def __init__(self, navigation_service: NavigationService, opentripmap_service: OpenTripMapService) -> None:
        self._navigation = navigation_service
        self._poi = opentripmap_service

    async def enrich_place(
        self, title: str, location_hint: str, destination: str
    ) -> dict | None:
        """
        Returns a real place-detail dict or None. Never fabricates a
        result when real data can't be found.
        """
        query = location_hint.strip() or f"{title}, {destination}"
        geocode = await self._navigation.geocode(query)
        if geocode is None:
            # Fall back to geocoding just the destination, so we can at
            # least search nearby even if the specific place name didn't
            # resolve on its own — still real data, just a wider search area.
            geocode = await self._navigation.geocode(destination)
        if geocode is None:
            return None

        candidates = await self._poi.search_pois(geocode["lat"], geocode["lon"], radius_m=3000)
        if not candidates:
            return None

        best = max(candidates, key=lambda c: _name_similarity(c["name"], title))
        if _name_similarity(best["name"], title) < MIN_NAME_SIMILARITY:
            return None  # no real POI close enough to this activity's name to responsibly attach

        details = await self._poi.get_place_details(best["xid"])
        if details is None:
            return None

        return {
            "matched_place_name": details["name"],
            "image_url": details["image_url"],
            "rating": details["rating"],
            "rating_scale": "1-7 (OpenTripMap popularity rating)" if details["rating"] is not None else None,
            "reviews_count": None,
            "reviews_count_note": "Not available from the current place data provider (OpenTripMap free tier).",
            "category": (details["kinds"][0].replace("_", " ").title() if details["kinds"] and details["kinds"][0] else None),
            "address": details["address"],
            "opening_hours": None,
            "opening_hours_note": "Not available from the current place data provider.",
            "estimated_ticket_price": None,
            "estimated_ticket_price_note": "Not available from the current place data provider.",
            "lat": details["lat"],
            "lon": details["lon"],
            "wikipedia_summary": details["wikipedia_summary"],
        }


_place_enrichment_service: PlaceEnrichmentService | None = None


def get_place_enrichment_service(
    navigation_service: NavigationService, opentripmap_service: OpenTripMapService
) -> PlaceEnrichmentService:
    global _place_enrichment_service
    if _place_enrichment_service is None:
        _place_enrichment_service = PlaceEnrichmentService(navigation_service, opentripmap_service)
    return _place_enrichment_service
