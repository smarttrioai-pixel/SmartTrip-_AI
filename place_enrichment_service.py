"""
Place Enrichment Service for SmartTrip AI.

The LLM proposes an activity or meal intent. This service resolves that intent
to a real place from OpenTripMap. It never fabricates a restaurant, rating,
image, address, coordinates, hours, or price.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from app.integrations.navigation_service import NavigationService
from app.integrations.opentripmap_service import OpenTripMapService

MIN_NAME_SIMILARITY = 0.35


def _name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


class PlaceEnrichmentService:
    def __init__(
        self,
        navigation_service: NavigationService,
        opentripmap_service: OpenTripMapService,
    ) -> None:
        self._navigation = navigation_service
        self._poi = opentripmap_service

    async def enrich_place(
        self,
        title: str,
        location_hint: str,
        destination: str,
        *,
        category: str | None = None,
        meal_type: str | None = None,
        food_query: str | None = None,
    ) -> dict | None:
        is_meal = (category or "").lower() == "meal" or bool(meal_type or food_query)

        if is_meal:
            # For meals, search for real food places rather than trying to
            # match a generated restaurant name. The LLM supplies cuisine/
            # food intent; the provider supplies the actual restaurant.
            search_text = food_query or location_hint or title
            geocode = await self._navigation.geocode(
                f"{search_text}, {destination}"
            )
            if geocode is None:
                geocode = await self._navigation.geocode(destination)
            if geocode is None:
                return None

            candidates = await self._poi.search_pois(
                geocode["lat"], geocode["lon"], radius_m=5000, category="foods"
            )
            if not candidates:
                return None

            # OpenTripMap's `rate` is a provider popularity score, not a
            # fabricated review rating. Prefer the highest available rate.
            best = max(candidates, key=lambda c: float(c.get("rate") or 0))
        else:
            query = location_hint.strip() or f"{title}, {destination}"
            geocode = await self._navigation.geocode(query)
            if geocode is None:
                geocode = await self._navigation.geocode(destination)
            if geocode is None:
                return None

            candidates = await self._poi.search_pois(
                geocode["lat"], geocode["lon"], radius_m=3000
            )
            if not candidates:
                return None

            best = max(candidates, key=lambda c: _name_similarity(c["name"], title))
            if _name_similarity(best["name"], title) < MIN_NAME_SIMILARITY:
                return None

        details = await self._poi.get_place_details(best["xid"])
        if details is None or not details.get("name"):
            return None

        kinds = details.get("kinds") or []
        return {
            "matched_place_name": details["name"],
            "image_url": details["image_url"],
            "rating": details["rating"],
            "rating_scale": (
                "1-7 (OpenTripMap popularity rating)"
                if details["rating"] is not None else None
            ),
            "reviews_count": None,
            "reviews_count_note": (
                "Not available from the current place data provider "
                "(OpenTripMap free tier)."
            ),
            "category": (
                kinds[0].replace("_", " ").title()
                if kinds and kinds[0] else (
                    "Restaurant" if is_meal else None
                )
            ),
            "address": details["address"],
            "opening_hours": None,
            "opening_hours_note": "Not available from the current place data provider.",
            "estimated_ticket_price": None,
            "estimated_ticket_price_note": (
                "Not available from the current place data provider."
            ),
            "lat": details["lat"],
            "lon": details["lon"],
            "wikipedia_summary": details["wikipedia_summary"],
        }


_place_enrichment_service: PlaceEnrichmentService | None = None


def get_place_enrichment_service(
    navigation_service: NavigationService,
    opentripmap_service: OpenTripMapService,
) -> PlaceEnrichmentService:
    global _place_enrichment_service
    if _place_enrichment_service is None:
        _place_enrichment_service = PlaceEnrichmentService(
            navigation_service, opentripmap_service
        )
    return _place_enrichment_service
