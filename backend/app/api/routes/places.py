"""
Place Enrichment API for SmartTrip AI.

Powers the rich place cards in the Itinerary and Saved Trips views —
real place metadata matched from Geoapify, not fabricated by the LLM.
Batched into one request per trip view load (up to 40 places) rather than
one HTTP round-trip per card.

Provider: Geoapify Places API
Architecture: PlaceEnrichmentService → GeoapifyProvider → Geoapify Places API
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser
from app.integrations.navigation_service import NavigationService, get_navigation_service
from app.integrations.geoapify_provider import GeoapifyProvider, get_geoapify_provider
from app.schemas.place import BatchEnrichRequest, BatchEnrichResponse, PlaceEnrichmentResult
from app.services.place_enrichment_service import PlaceEnrichmentService, get_place_enrichment_service

router = APIRouter(prefix="/places", tags=["Places"])


def _get_enrichment_service(
    navigation_service: NavigationService = Depends(get_navigation_service),
    geoapify_provider: GeoapifyProvider = Depends(get_geoapify_provider),
) -> PlaceEnrichmentService:
    return get_place_enrichment_service(navigation_service, geoapify_provider)


@router.post(
    "/enrich",
    response_model=BatchEnrichResponse,
    summary="Enrich itinerary places with real data from Geoapify",
)
async def enrich_places(
    request: BatchEnrichRequest,
    current_user: CurrentUser,
    enrichment_service: PlaceEnrichmentService = Depends(_get_enrichment_service),
) -> BatchEnrichResponse:
    results: list[PlaceEnrichmentResult] = []
    used_place_ids: set[str] = set()

    for place in request.places:
        data = await enrichment_service.enrich_place(
            place.title,
            place.location_hint,
            request.destination,
            category=place.category,
            meal_type=place.meal_type,
            food_query=place.food_query,
            used_place_ids=used_place_ids,
        )
        if data is None:
            results.append(PlaceEnrichmentResult(found=False))
        else:
            result = PlaceEnrichmentResult(found=True, **data)
            results.append(result)
            # Track used place IDs to prevent duplicate restaurants
            if data.get("source_id"):
                used_place_ids.add(data["source_id"])

    return BatchEnrichResponse(results=results)
