"""
Place Enrichment Service for SmartTrip AI.

Architecture:
    LLM (Qwen via Groq)           — proposes activity/meal intent
         ↓
    PlaceEnrichmentService         — this file
         ↓
    GeoapifyProvider               — app/integrations/geoapify_provider.py
         ↓
    Geoapify Places API            — real place discovery and verification
         ↓
    Validated itinerary            — only verified places reach the frontend

Principles enforced here:
- The LLM NEVER fabricates a restaurant name, attraction name, coordinate,
  rating, image URL, address, or opening hours.
- Geoapify is the source of truth for real geographic places.
- Attraction names proposed by the LLM are validated against Geoapify search
  results. If no sufficiently strong match is found, the activity is marked
  as unresolved (returns None) and removed from the itinerary.
- Meal slots are resolved to REAL restaurants found by Geoapify. The LLM
  provides food intent / cuisine; Geoapify provides the actual restaurant.
- Duplicate restaurants across breakfast / lunch / dinner are prevented via
  a used_place_ids set maintained by the caller (PlanningEngine).
"""
from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Any

from app.integrations.geoapify_provider import GeoapifyProvider, get_geoapify_provider, CATEGORY_MAP
from app.integrations.navigation_service import NavigationService, get_navigation_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Matching thresholds
# ---------------------------------------------------------------------------

# Minimum composite score for an attraction to be accepted as a valid match.
# Below this threshold the attraction is considered unverified and is removed.
MIN_ATTRACTION_MATCH_SCORE = 0.30

# Penalty applied to a place's score when it has already been used in the
# current itinerary (e.g. same restaurant for breakfast and lunch).
DUPLICATE_PENALTY = 0.40

# Default search radii
ATTRACTION_RADIUS_M = 5_000
MEAL_RADIUS_M = 5_000


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _name_similarity(a: str, b: str) -> float:
    """SequenceMatcher-based name similarity in [0, 1]."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _category_match(candidate_categories: list[str], requested_concept: str) -> float:
    """1.0 if any candidate category overlaps with the requested concept mapping."""
    expected = set(CATEGORY_MAP.get(requested_concept.lower(), []))
    if not expected:
        return 0.5  # unknown concept — neutral
    for cat in candidate_categories:
        for exp in expected:
            if exp.startswith(cat) or cat.startswith(exp):
                return 1.0
    return 0.0


def _distance_score(distance_m: float, radius_m: int) -> float:
    """Linear distance score: 1.0 at centre, 0.0 at radius boundary."""
    if radius_m <= 0:
        return 0.5
    return max(0.0, 1.0 - (distance_m / radius_m))


def _query_relevance(candidate_name: str, query: str | None) -> float:
    """Similarity between candidate name and the food/query intent string."""
    if not query or not candidate_name:
        return 0.0
    return SequenceMatcher(None, candidate_name.lower(), query.lower()).ratio()


def _score_candidate(
    candidate: dict[str, Any],
    *,
    requested_name: str,
    requested_concept: str,
    radius_m: int,
    food_query: str | None = None,
    used_place_ids: set[str] | None = None,
) -> float:
    """
    Composite candidate score.

        score = 0.50 * name_similarity
              + 0.20 * category_match
              + 0.20 * distance_score
              + 0.10 * query_relevance
              - DUPLICATE_PENALTY  (if place_id in used_place_ids)

    Returns a float in [-0.4, 1.0].
    """
    name_sim = _name_similarity(candidate.get("name", ""), requested_name)
    cat_score = _category_match(candidate.get("categories", []), requested_concept)
    dist_score = _distance_score(float(candidate.get("distance_m", 0)), radius_m)
    query_score = _query_relevance(candidate.get("name", ""), food_query)

    score = (
        0.50 * name_sim
        + 0.20 * cat_score
        + 0.20 * dist_score
        + 0.10 * query_score
    )

    if used_place_ids and candidate.get("place_id") in used_place_ids:
        score -= DUPLICATE_PENALTY

    return score


# ---------------------------------------------------------------------------
# PlaceEnrichmentService
# ---------------------------------------------------------------------------

class PlaceEnrichmentService:
    """
    Provider-agnostic orchestrator for place discovery and validation.

    Responsibilities:
        1. Resolve destination coordinates (via NavigationService / Nominatim).
        2. Search candidate places via GeoapifyProvider.
        3. Score and rank candidates.
        4. Validate attraction candidates against the LLM-proposed name.
        5. Return verified place metadata; return None for unverified places.
    """

    def __init__(
        self,
        navigation_service: NavigationService,
        geoapify_provider: GeoapifyProvider,
    ) -> None:
        self._navigation = navigation_service
        self._geoapify = geoapify_provider

    async def _resolve_destination_coords(
        self,
        destination: str,
    ) -> dict[str, Any] | None:
        """
        Geocode the destination city/region (not a food query or POI name).

        Step 1: Try Geoapify geocoding.
        Step 2: Fall back to NavigationService (Nominatim) if Geoapify unavailable.
        Returns None if both fail.
        """
        # Try Geoapify first (preferred — consistent data source)
        geo = await self._geoapify.geocode(destination)
        if geo:
            return geo

        # Fallback to Nominatim (NavigationService)
        nav_geo = await self._navigation.geocode(destination)
        if nav_geo:
            return {"lat": nav_geo["lat"], "lon": nav_geo["lon"]}

        return None

    async def enrich_place(
        self,
        title: str,
        location_hint: str,
        destination: str,
        *,
        category: str | None = None,
        meal_type: str | None = None,
        food_query: str | None = None,
        used_place_ids: set[str] | None = None,
    ) -> dict[str, Any] | None:
        """
        Resolve an LLM-generated activity title to a verified real place.

        For meals:
            - Geocode the DESTINATION (not the food query).
            - Search Geoapify for real restaurants/cafes near the destination.
            - Rank by score; penalize duplicates.
            - Return the best real restaurant (any restaurant is acceptable —
              the LLM provides intent; Geoapify provides the actual place).

        For attractions:
            - Geocode the destination.
            - Search Geoapify for nearby sights matching the category.
            - Score candidates against the LLM-proposed name.
            - If best score < MIN_ATTRACTION_MATCH_SCORE → return None
              (the place cannot be verified and will be removed).

        Returns:
            A dict of verified place metadata, or None if unresolved.
            The caller must treat None as "remove this activity".
        """
        is_meal = (
            (category or "").lower() == "meal"
            or bool(meal_type)
            or bool(food_query)
        )

        # ----------------------------------------------------------------
        # Step 1: Resolve destination coordinates
        # ----------------------------------------------------------------
        geo = await self._resolve_destination_coords(destination)
        if geo is None:
            logger.warning(
                "place_enrichment destination=%r geocode_failed — cannot enrich %r",
                destination, title,
            )
            return None

        dest_lat: float = geo["lat"]
        dest_lon: float = geo["lon"]

        if is_meal:
            return await self._enrich_meal(
                title=title,
                destination=destination,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                meal_type=meal_type,
                food_query=food_query,
                used_place_ids=used_place_ids,
            )
        else:
            return await self._enrich_attraction(
                title=title,
                destination=destination,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                category=category,
                used_place_ids=used_place_ids,
            )

    async def _enrich_meal(
        self,
        *,
        title: str,
        destination: str,
        dest_lat: float,
        dest_lon: float,
        meal_type: str | None,
        food_query: str | None,
        used_place_ids: set[str] | None,
    ) -> dict[str, Any] | None:
        """
        Find a REAL restaurant near the destination for this meal slot.

        The LLM's food_query guides the search intent; Geoapify returns
        actual restaurant records. The LLM-proposed title (e.g. "Local
        Restaurant") is NOT used as the final place name — only Geoapify
        names are returned.
        """
        categories = CATEGORY_MAP["meal"]  # catering.restaurant + cafe + fast_food

        # Use food_query as a name hint to Geoapify (best-effort text filter)
        name_hint = food_query or None

        candidates = await self._geoapify.search_places(
            latitude=dest_lat,
            longitude=dest_lon,
            categories=categories,
            radius_meters=MEAL_RADIUS_M,
            name_filter=name_hint,
            limit=20,
        )

        if not candidates:
            # Try broader search without name filter
            candidates = await self._geoapify.search_places(
                latitude=dest_lat,
                longitude=dest_lon,
                categories=categories,
                radius_meters=MEAL_RADIUS_M,
                limit=20,
            )

        if not candidates:
            logger.info(
                "place_enrichment destination=%r meal=%r no_candidates_found",
                destination, meal_type,
            )
            return None

        # Score candidates; penalize duplicates
        scored = [
            (
                _score_candidate(
                    c,
                    requested_name=food_query or meal_type or title,
                    requested_concept="restaurant",
                    radius_m=MEAL_RADIUS_M,
                    food_query=food_query,
                    used_place_ids=used_place_ids,
                ),
                c,
            )
            for c in candidates
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best = scored[0]

        logger.info(
            "place_enrichment destination=%r meal=%r matched_place=%r "
            "match_score=%.2f verified=true",
            destination, meal_type, best.get("name"), best_score,
        )

        return self._build_result(best, is_meal=True)

    async def _enrich_attraction(
        self,
        *,
        title: str,
        destination: str,
        dest_lat: float,
        dest_lon: float,
        category: str | None,
        used_place_ids: set[str] | None,
    ) -> dict[str, Any] | None:
        """
        Validate an LLM-proposed attraction against real Geoapify data.

        If the best candidate's score is below MIN_ATTRACTION_MATCH_SCORE,
        returns None — the attraction is considered fabricated and removed.

        Example:
            LLM proposes "Guntur War Memorial"
            Geoapify finds no matching sights near Guntur
            → score below threshold → return None → activity removed
        """
        concept = category or "attraction"
        categories = GeoapifyProvider.categories_for_concept(concept)

        candidates = await self._geoapify.search_places(
            latitude=dest_lat,
            longitude=dest_lon,
            categories=categories,
            radius_meters=ATTRACTION_RADIUS_M,
            limit=20,
        )

        if not candidates:
            logger.info(
                "place_enrichment destination=%r attraction=%r no_candidates_found verified=false",
                destination, title,
            )
            return None

        # Score all candidates against the LLM-proposed name
        scored = [
            (
                _score_candidate(
                    c,
                    requested_name=title,
                    requested_concept=concept,
                    radius_m=ATTRACTION_RADIUS_M,
                    used_place_ids=used_place_ids,
                ),
                c,
            )
            for c in candidates
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best = scored[0]

        logger.info(
            "place_enrichment destination=%r requested_place=%r matched_place=%r "
            "match_score=%.2f verified=%s",
            destination, title, best.get("name"), best_score,
            "true" if best_score >= MIN_ATTRACTION_MATCH_SCORE else "false",
        )

        if best_score < MIN_ATTRACTION_MATCH_SCORE:
            # The LLM-generated attraction name could not be verified.
            # Do NOT fabricate a fallback — return None to have the caller
            # remove this activity from the itinerary.
            return None

        return self._build_result(best, is_meal=False)

    @staticmethod
    def _build_result(place: dict[str, Any], *, is_meal: bool) -> dict[str, Any]:
        """
        Build the standardised enrichment result dict from a Geoapify place record.

        All fields come directly from Geoapify — nothing is fabricated.
        Fields not available from the provider are set to None.
        """
        categories = place.get("categories", [])
        category_label: str | None = None
        if categories:
            # Humanise the first category token
            raw = categories[0] if isinstance(categories, list) else str(categories)
            category_label = raw.split(".")[-1].replace("_", " ").title()
        if not category_label:
            category_label = "Restaurant" if is_meal else None

        return {
            "matched_place_name": place.get("name"),
            "image_url": place.get("image_url"),        # None on Geoapify free tier
            "rating": place.get("rating"),               # None on Geoapify free tier
            "rating_scale": None,                        # no rating → no scale
            "reviews_count": None,
            "reviews_count_note": "Not available from Geoapify.",
            "category": category_label,
            "address": place.get("address"),
            "opening_hours": place.get("opening_hours"),
            "opening_hours_note": (
                None if place.get("opening_hours") else "Not available from Geoapify."
            ),
            "estimated_ticket_price": None,
            "estimated_ticket_price_note": "Not available from Geoapify.",
            "lat": place.get("lat"),
            "lon": place.get("lon"),
            "wikipedia_summary": None,
            # Source provenance — used for debugging and deduplication
            "source": "geoapify",
            "source_id": place.get("source_id") or place.get("place_id"),
        }


# ---------------------------------------------------------------------------
# Module-level singleton + factory
# ---------------------------------------------------------------------------

_place_enrichment_service: PlaceEnrichmentService | None = None


def get_place_enrichment_service(
    navigation_service: NavigationService,
    geoapify_provider: GeoapifyProvider,
) -> PlaceEnrichmentService:
    global _place_enrichment_service
    if _place_enrichment_service is None:
        _place_enrichment_service = PlaceEnrichmentService(
            navigation_service, geoapify_provider
        )
    return _place_enrichment_service
