"""
Place Enrichment Service for SmartTrip AI.

Architecture (updated):
    LLM (Qwen via Groq)           — outputs PLANNING INTENT (slot_intent, place_query)
         ↓
    PlaceEnrichmentService         — this file
         ├─ PRIMARY: GooglePlacesProvider
         │       ↓
         │   TouristRanker          — tourist relevance scoring
         │       ↓
         │   PlaceConsistencyValidator — description mismatch detection
         │
         └─ FALLBACK: GeoapifyProvider (if Google fails or returns 0 results)
                       and ENABLE_GEOAPIFY_FALLBACK=true

Principles enforced here:
- Qwen NEVER produces final place names. It produces planning INTENT.
- Google Places is the source of truth for real geographic places.
- Tourist relevance ranking ensures a juice shop never beats a temple.
- Generic businesses are rejected from attraction slots.
- Duplicate places are prevented via place_id tracking (not string matching).
- If both providers fail → return None → activity removed from itinerary.
- No fabrication under any circumstances.
"""
from __future__ import annotations

import logging
from typing import Any

from app.cognitive.place_consistency import PlaceConsistencyValidator, get_place_consistency_validator
from app.cognitive.tourist_ranker import TouristRanker, MIN_TOURIST_RELEVANCE, get_tourist_ranker
from app.core.config import get_settings
from app.integrations.geoapify_provider import GeoapifyProvider, get_geoapify_provider, CATEGORY_MAP
from app.integrations.google_places_provider import GooglePlacesProvider, get_google_places_provider
from app.integrations.navigation_service import NavigationService, get_navigation_service
from app.integrations.place_provider import PlaceCandidate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Search configuration
# ---------------------------------------------------------------------------
ATTRACTION_RADIUS_M = 8_000   # Wider radius for attractions
MEAL_RADIUS_M = 5_000

# Minimum attraction results from Google before triggering Geoapify fallback
_MIN_GOOGLE_ATTRACTION_CANDIDATES = 2
_MIN_GOOGLE_RESTAURANT_CANDIDATES = 2

# ---------------------------------------------------------------------------
# Category → attraction search queries
# Used to build multiple targeted Google queries per slot intent
# ---------------------------------------------------------------------------
_CATEGORY_QUERIES: dict[str, list[str]] = {
    "attraction": [
        "tourist attractions",
        "historical landmarks",
        "famous places",
    ],
    "culture": [
        "museums cultural sites",
        "art galleries",
        "cultural centers",
    ],
    "nature": [
        "parks nature reserves",
        "gardens viewpoints",
        "scenic spots",
    ],
    "museum": [
        "museums",
        "heritage sites exhibitions",
    ],
    "sights": [
        "tourist attractions landmarks",
        "historical monuments",
    ],
    "religious": [
        "temples shrines",
        "mosques churches",
        "religious sites",
    ],
    "shopping": [
        "markets bazaars",
        "local shopping areas",
    ],
}


def _build_attraction_query(slot_intent: str, category: str, destination: str) -> str:
    """Build a targeted Google Places search query for an attraction slot."""
    # Use slot_intent if it contains useful terms
    if slot_intent and len(slot_intent) > 5:
        return f"{slot_intent} in {destination}"

    # Category-based generic query
    base_queries = _CATEGORY_QUERIES.get(category.lower(), ["tourist attractions"])
    return f"{base_queries[0]} in {destination}"


def _candidate_to_enrichment(
    candidate: PlaceCandidate,
    *,
    is_meal: bool,
) -> dict[str, Any]:
    """Convert a PlaceCandidate to the enrichment result dict used by PlanningEngine."""
    # Humanize the primary type
    category_label: str | None = None
    if candidate.types:
        t = candidate.types[0]
        category_label = t.replace("_", " ").title()
    if not category_label:
        category_label = "Restaurant" if is_meal else None

    return {
        "matched_place_name": candidate.name,
        "place_id": candidate.place_id,
        "image_url": None,
        "rating": candidate.rating,
        "rating_scale": 5.0 if candidate.rating is not None else None,
        "user_ratings_total": candidate.user_ratings_total,
        "price_level": candidate.price_level,
        "category": category_label,
        "place_types": candidate.types,
        "address": candidate.address,
        "lat": candidate.lat,
        "lon": candidate.lon,
        "opening_hours": candidate.opening_hours,
        "opening_hours_note": (
            None if candidate.opening_hours else "Not available from provider."
        ),
        "business_status": candidate.business_status,
        "estimated_ticket_price": None,
        "estimated_ticket_price_note": "Not available from provider.",
        "wikipedia_summary": None,
        "tourist_relevance": round(candidate.tourist_relevance, 3),
        "source": candidate.source,
        "source_id": candidate.place_id,
        "verified": True,
    }


class PlaceEnrichmentService:
    """
    Provider-agnostic orchestrator for place discovery and validation.

    Primary flow:
        1. Resolve destination coordinates.
        2. Google Places (primary).
        3. TouristRanker — score candidates.
        4. PlaceConsistencyValidator — validate activity/place match.
        5. Return verified place metadata.

    Fallback:
        If Google returns 0 candidates or is unavailable →
        GeoapifyProvider (if ENABLE_GEOAPIFY_FALLBACK=true).

    Returns None when no verified place is found — never fabricates.
    """

    def __init__(
        self,
        navigation_service: NavigationService,
        geoapify_provider: GeoapifyProvider,
        google_places_provider: GooglePlacesProvider,
        tourist_ranker: TouristRanker,
        place_consistency_validator: PlaceConsistencyValidator,
    ) -> None:
        self._navigation = navigation_service
        self._geoapify = geoapify_provider
        self._google = google_places_provider
        self._ranker = tourist_ranker
        self._validator = place_consistency_validator
        self._settings = get_settings()

    @property
    def _google_enabled(self) -> bool:
        return (
            self._settings.PLACE_PROVIDER == "google"
            and bool(self._settings.GOOGLE_PLACES_API_KEY)
        )

    @property
    def _geoapify_fallback_enabled(self) -> bool:
        return self._settings.ENABLE_GEOAPIFY_FALLBACK and bool(self._settings.GEOAPIFY_API_KEY)

    async def _resolve_destination_coords(self, destination: str) -> dict[str, Any] | None:
        """
        Geocode destination. Tries Google first, then Geoapify, then Nominatim.
        Returns None if all fail.
        """
        # Try Google geocoding
        if self._google_enabled:
            try:
                geo = await self._google.geocode(destination)
                if geo:
                    return {"lat": geo.lat, "lon": geo.lon}
            except Exception as e:
                logger.warning("Google geocode failed for %r: %s", destination, e)

        # Try Geoapify geocoding
        if self._settings.GEOAPIFY_API_KEY:
            try:
                geo = await self._geoapify.geocode(destination)
                if geo:
                    return {"lat": geo["lat"], "lon": geo["lon"]}
            except Exception as e:
                logger.warning("Geoapify geocode failed for %r: %s", destination, e)

        # Fallback to Nominatim (NavigationService)
        try:
            nav_geo = await self._navigation.geocode(destination)
            if nav_geo:
                return {"lat": nav_geo["lat"], "lon": nav_geo["lon"]}
        except Exception as e:
            logger.warning("Nominatim geocode failed for %r: %s", destination, e)

        return None

    async def enrich_place(
        self,
        title: str,
        location_hint: str,
        destination: str,
        *,
        slot_intent: str | None = None,
        place_query: str | None = None,
        place_type_hint: str | None = None,
        category: str | None = None,
        meal_type: str | None = None,
        food_query: str | None = None,
        used_place_ids: set[str] | None = None,
        user_preferences: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """
        Resolve a planning intent to a verified real place.

        Args:
            title:          Qwen-generated slot title (kept as fallback hint only).
            slot_intent:    Qwen planning intent string (preferred).
            place_query:    Targeted search query from Qwen.
            place_type_hint: Qwen-suggested Google type hint.
            category:       Activity category (meal|attraction|culture|nature|museum...).
            meal_type:      breakfast|lunch|dinner (for meal slots).
            food_query:     Food/cuisine search query from Qwen.
            used_place_ids: Set of already-used place IDs (deduplication).
            user_preferences: User memory preferences for ranking.

        Returns:
            Verified enrichment dict or None.
        """
        is_meal = (
            (category or "").lower() == "meal"
            or bool(meal_type)
            or bool(food_query)
        )

        # Resolve destination coordinates
        geo = await self._resolve_destination_coords(destination)
        if geo is None:
            logger.warning(
                "place_enrichment destination=%r geocode_failed — cannot enrich %r",
                destination, title,
            )
            return None

        dest_lat: float = geo["lat"]
        dest_lon: float = geo["lon"]

        effective_intent = slot_intent or title or ""
        effective_query = place_query or food_query or effective_intent
        effective_category = category or ("meal" if is_meal else "attraction")

        if is_meal:
            return await self._enrich_meal(
                destination=destination,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                meal_type=meal_type,
                food_query=food_query or effective_query,
                used_place_ids=used_place_ids,
                user_preferences=user_preferences,
            )
        else:
            return await self._enrich_attraction(
                title=title,
                destination=destination,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                slot_intent=effective_intent,
                place_query=effective_query,
                category=effective_category,
                used_place_ids=used_place_ids,
                user_preferences=user_preferences,
            )

    # ------------------------------------------------------------------
    # Attraction enrichment
    # ------------------------------------------------------------------

    async def _enrich_attraction(
        self,
        *,
        title: str,
        destination: str,
        dest_lat: float,
        dest_lon: float,
        slot_intent: str,
        place_query: str,
        category: str,
        used_place_ids: set[str] | None,
        user_preferences: list[str] | None,
    ) -> dict[str, Any] | None:
        """Find a real tourist attraction via Google (primary) or Geoapify (fallback)."""

        candidates: list[PlaceCandidate] = []
        provider_used = "none"

        # --- Google PRIMARY ---
        if self._google_enabled:
            query = _build_attraction_query(slot_intent, category, destination)
            try:
                raw = await self._google.search_attractions(
                    lat=dest_lat,
                    lon=dest_lon,
                    query=query,
                    radius_m=ATTRACTION_RADIUS_M,
                    limit=25,
                )
                if raw:
                    candidates = raw
                    provider_used = "google"
                    logger.info(
                        "place_enrichment provider=google operation=attraction "
                        "destination=%r query=%r candidates=%d",
                        destination, query, len(candidates),
                    )
            except Exception as exc:
                logger.warning(
                    "Google attraction search failed for %r: %s", destination, exc
                )

        # --- Geoapify FALLBACK ---
        if len(candidates) < _MIN_GOOGLE_ATTRACTION_CANDIDATES and self._geoapify_fallback_enabled:
            try:
                concept = category or "attraction"
                geo_categories = GeoapifyProvider.categories_for_concept(concept)
                geo_results = await self._geoapify.search_places(
                    latitude=dest_lat,
                    longitude=dest_lon,
                    categories=geo_categories,
                    radius_meters=ATTRACTION_RADIUS_M,
                    limit=20,
                )
                if geo_results:
                    # Convert Geoapify results to PlaceCandidate
                    geo_candidates = [
                        PlaceCandidate(
                            place_id=r.get("place_id") or r.get("source_id") or "",
                            name=r.get("name") or "",
                            lat=r.get("lat", dest_lat),
                            lon=r.get("lon", dest_lon),
                            address=r.get("address"),
                            rating=None,
                            user_ratings_total=None,
                            types=[c.split(".")[-1] for c in r.get("categories", [])],
                            opening_hours=r.get("opening_hours"),
                            distance_m=float(r.get("distance_m", 0)),
                            source="geoapify",
                        )
                        for r in geo_results if r.get("name")
                    ]
                    candidates = candidates + geo_candidates
                    provider_used = "geoapify" if not candidates else "google+geoapify"
                    logger.info(
                        "place_enrichment provider=geoapify_fallback operation=attraction "
                        "destination=%r candidates=%d",
                        destination, len(geo_candidates),
                    )
            except Exception as exc:
                logger.warning("Geoapify fallback failed for %r: %s", destination, exc)

        if not candidates:
            logger.info(
                "place_enrichment destination=%r attraction=%r no_candidates provider=%s",
                destination, title, provider_used,
            )
            return None

        # --- Tourist Ranking ---
        ranked = self._ranker.score_candidates(
            candidates,
            slot_intent=slot_intent,
            user_preferences=user_preferences or [],
            radius_m=ATTRACTION_RADIUS_M,
            used_place_ids=used_place_ids,
        )

        # --- Apply minimum tourist relevance threshold ---
        passing = [c for c in ranked if c.tourist_relevance >= MIN_TOURIST_RELEVANCE]

        if not passing:
            logger.info(
                "place_enrichment destination=%r attraction=%r "
                "all_candidates_below_threshold=%.2f top_score=%.2f "
                "top_name=%r top_types=%s",
                destination, title, MIN_TOURIST_RELEVANCE,
                ranked[0].tourist_relevance if ranked else 0.0,
                ranked[0].name if ranked else "none",
                ranked[0].types[:3] if ranked else [],
            )
            return None  # Quality > quantity — no fabrication

        best = passing[0]

        # --- Place validity check for this slot ---
        if not self._validator.is_valid_attraction(best.types, category):
            logger.info(
                "PLACE_VALIDATION place=%r types=%s category=%s decision=reject "
                "reason=wrong_category_for_slot",
                best.name, best.types[:3], category,
            )
            # Try next candidate
            for alt in passing[1:]:
                if self._validator.is_valid_attraction(alt.types, category):
                    best = alt
                    break
            else:
                return None

        logger.info(
            "place_enrichment destination=%r attraction=%r "
            "matched_place=%r score=%.2f types=%s provider=%s",
            destination, title, best.name, best.tourist_relevance,
            best.types[:3], best.source,
        )

        result = _candidate_to_enrichment(best, is_meal=False)
        result["provider_used"] = best.source
        return result

    # ------------------------------------------------------------------
    # Meal enrichment
    # ------------------------------------------------------------------

    async def _enrich_meal(
        self,
        *,
        destination: str,
        dest_lat: float,
        dest_lon: float,
        meal_type: str | None,
        food_query: str,
        used_place_ids: set[str] | None,
        user_preferences: list[str] | None,
    ) -> dict[str, Any] | None:
        """Find a REAL restaurant for a meal slot."""

        candidates: list[PlaceCandidate] = []
        provider_used = "none"

        # Combine food_query with destination context
        effective_query = food_query or f"restaurant {destination}"
        if destination.lower() not in effective_query.lower():
            effective_query = f"{effective_query} {destination}"

        # --- Google PRIMARY ---
        if self._google_enabled:
            try:
                raw = await self._google.search_restaurants(
                    lat=dest_lat,
                    lon=dest_lon,
                    food_query=effective_query,
                    meal_type=meal_type,
                    radius_m=MEAL_RADIUS_M,
                    limit=20,
                )
                if raw:
                    candidates = raw
                    provider_used = "google"
            except Exception as exc:
                logger.warning("Google restaurant search failed for %r: %s", destination, exc)

        # --- Geoapify FALLBACK ---
        if len(candidates) < _MIN_GOOGLE_RESTAURANT_CANDIDATES and self._geoapify_fallback_enabled:
            try:
                geo_categories = CATEGORY_MAP["meal"]
                geo_results = await self._geoapify.search_places(
                    latitude=dest_lat,
                    longitude=dest_lon,
                    categories=geo_categories,
                    radius_meters=MEAL_RADIUS_M,
                    limit=20,
                )
                if geo_results:
                    geo_candidates = [
                        PlaceCandidate(
                            place_id=r.get("place_id") or r.get("source_id") or "",
                            name=r.get("name") or "",
                            lat=r.get("lat", dest_lat),
                            lon=r.get("lon", dest_lon),
                            address=r.get("address"),
                            rating=None,
                            types=["restaurant"],
                            opening_hours=r.get("opening_hours"),
                            distance_m=float(r.get("distance_m", 0)),
                            source="geoapify",
                        )
                        for r in geo_results if r.get("name")
                    ]
                    candidates = candidates + geo_candidates
                    provider_used = "geoapify" if not candidates else "google+geoapify"
            except Exception as exc:
                logger.warning("Geoapify meal fallback failed for %r: %s", destination, exc)

        if not candidates:
            logger.info(
                "place_enrichment destination=%r meal=%r no_candidates",
                destination, meal_type,
            )
            return None

        # --- Restaurant Ranking ---
        ranked = self._ranker.score_restaurant_candidates(
            candidates,
            food_query=food_query or "",
            meal_type=meal_type,
            user_preferences=user_preferences or [],
            radius_m=MEAL_RADIUS_M,
            used_place_ids=used_place_ids,
        )

        best = ranked[0]

        logger.info(
            "place_enrichment destination=%r meal=%r matched_place=%r "
            "score=%.2f rating=%s provider=%s",
            destination, meal_type, best.name, best.tourist_relevance,
            best.rating, best.source,
        )

        result = _candidate_to_enrichment(best, is_meal=True)
        result["provider_used"] = best.source
        return result


# ---------------------------------------------------------------------------
# Module-level singleton + factory
# ---------------------------------------------------------------------------

_place_enrichment_service: PlaceEnrichmentService | None = None


def get_place_enrichment_service(
    navigation_service: NavigationService,
    geoapify_provider: GeoapifyProvider,
    google_places_provider: GooglePlacesProvider | None = None,
    tourist_ranker: TouristRanker | None = None,
    place_consistency_validator: PlaceConsistencyValidator | None = None,
) -> PlaceEnrichmentService:
    global _place_enrichment_service
    if _place_enrichment_service is None:
        _place_enrichment_service = PlaceEnrichmentService(
            navigation_service=navigation_service,
            geoapify_provider=geoapify_provider,
            google_places_provider=google_places_provider or get_google_places_provider(),
            tourist_ranker=tourist_ranker or get_tourist_ranker(),
            place_consistency_validator=place_consistency_validator or get_place_consistency_validator(),
        )
    return _place_enrichment_service
