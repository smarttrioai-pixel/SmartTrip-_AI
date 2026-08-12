"""
Place Enrichment API for SmartTrip AI.

Powers the rich place cards in the Itinerary and Saved Trips views —
real images/ratings/addresses matched from OpenTripMap, not fabricated.
Batched into one request per trip view load (up to 40 places) rather than
one HTTP round-trip per card.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser
from app.integrations.navigation_service import NavigationService, get_navigation_service
from app.integrations.opentripmap_service import OpenTripMapService, get_opentripmap_service
from app.schemas.place import BatchEnrichRequest, BatchEnrichResponse, PlaceEnrichmentResult
from app.services.place_enrichment_service import PlaceEnrichmentService, get_place_enrichment_service

router = APIRouter(prefix="/places", tags=["Places"])


def _get_enrichment_service(
    navigation_service: NavigationService = Depends(get_navigation_service),
    opentripmap_service: OpenTripMapService = Depends(get_opentripmap_service),
) -> PlaceEnrichmentService:
    return get_place_enrichment_service(navigation_service, opentripmap_service)


@router.post("/enrich", response_model=BatchEnrichResponse, summary="Enrich itinerary places with real photo/rating/address data")
async def enrich_places(
    request: BatchEnrichRequest,
    current_user: CurrentUser,
    enrichment_service: PlaceEnrichmentService = Depends(_get_enrichment_service),
) -> BatchEnrichResponse:
    results: list[PlaceEnrichmentResult] = []
    for place in request.places:
        data = await enrichment_service.enrich_place(
            place.title,
            place.location_hint,
            request.destination,
            category=place.category,
            meal_type=place.meal_type,
            food_query=place.food_query,
        )
        if data is None:
            results.append(PlaceEnrichmentResult(found=False))
        else:
            results.append(PlaceEnrichmentResult(found=True, **data))
    return BatchEnrichResponse(results=results)
