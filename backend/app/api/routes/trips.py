"""
Trip API routes — SmartTrip AI

Endpoints:
  POST   /trips/generate                               Generate new trip
  GET    /trips                                        List user's trips
  GET    /trips/{trip_id}                              Get single trip
  PATCH  /trips/{trip_id}/save                         Mark saved/unsaved
  DELETE /trips/{trip_id}                              Delete trip

  POST   /trips/{trip_id}/modify                       Natural-language modification
  POST   /trips/{trip_id}/activities/{id}/alternatives Get real alternatives
  POST   /trips/{trip_id}/activities/{id}/replace      Replace with chosen alternative
  POST   /trips/{trip_id}/activities/{id}/move         Move to different time/day
  DELETE /trips/{trip_id}/activities/{id}              Remove activity
  POST   /trips/{trip_id}/activities/reorder           Reorder day activities
"""
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    CurrentUser,
    get_trip_planner_service,
    get_trip_repository,
    get_itinerary_modifier,
    get_alternatives_service,
)
from app.schemas.trip import (
    GenerateItineraryRequest,
    SaveTripRequest,
    TripResponse,
    ModifyItineraryRequest,
    ModifyItineraryResponse,
    AlternativesRequest,
    AlternativesResponse,
    ReplaceActivityRequest,
    MoveActivityRequest,
    ReorderRequest,
)
from app.services.trip_service import TripPlannerService
from app.services.itinerary_modifier import ItineraryModifier
from app.services.alternatives_service import AlternativeRecommendationService
from app.repositories.trip_repository import TripRepository

router = APIRouter(prefix="/trips", tags=["AI Trip Planner"])


# ---------------------------------------------------------------------------
# Core trip CRUD
# ---------------------------------------------------------------------------

@router.post("/generate", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
async def generate_itinerary(
    payload: GenerateItineraryRequest,
    current_user: CurrentUser,
    trip_service: Annotated[TripPlannerService, Depends(get_trip_planner_service)],
) -> TripResponse:
    if payload.end_date < payload.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be on or after start_date",
        )
    try:
        return await trip_service.generate_itinerary(current_user.id, payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("", response_model=list[TripResponse])
async def list_trips(
    current_user: CurrentUser,
    trip_service: Annotated[TripPlannerService, Depends(get_trip_planner_service)],
    saved_only: bool = False,
) -> list[TripResponse]:
    return await trip_service.list_trips(current_user.id, saved_only=saved_only)


@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(
    trip_id: str,
    current_user: CurrentUser,
    trip_repo: Annotated[TripRepository, Depends(get_trip_repository)],
) -> TripResponse:
    trip = await trip_repo.get_by_id(trip_id)
    if trip is None or trip.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")
    return TripResponse(
        id=trip.id,
        destination=trip.destination,
        start_date=trip.start_date,
        end_date=trip.end_date,
        budget=trip.budget,
        currency=trip.currency,
        travel_style=trip.travel_style,
        days=trip.days,
        estimated_total_cost=trip.estimated_total_cost,
        is_saved=trip.is_saved,
    )


@router.patch("/{trip_id}/save", status_code=status.HTTP_204_NO_CONTENT)
async def save_trip(
    trip_id: str,
    payload: SaveTripRequest,
    current_user: CurrentUser,
    trip_service: Annotated[TripPlannerService, Depends(get_trip_planner_service)],
) -> None:
    await trip_service.set_saved(current_user.id, trip_id, payload.is_saved)


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(
    trip_id: str,
    current_user: CurrentUser,
    trip_service: Annotated[TripPlannerService, Depends(get_trip_planner_service)],
) -> None:
    await trip_service.delete_trip(trip_id)


# ---------------------------------------------------------------------------
# Itinerary modification
# ---------------------------------------------------------------------------

@router.post("/{trip_id}/modify", response_model=ModifyItineraryResponse)
async def modify_itinerary(
    trip_id: str,
    payload: ModifyItineraryRequest,
    current_user: CurrentUser,
    trip_repo: Annotated[TripRepository, Depends(get_trip_repository)],
    modifier: Annotated[ItineraryModifier, Depends(get_itinerary_modifier)],
) -> ModifyItineraryResponse:
    """Natural-language itinerary modification via OpenAI intent parsing."""
    trip = await trip_repo.get_by_id(trip_id)
    if trip is None or trip.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")
    try:
        result = await modifier.modify_by_intent(trip, payload.user_message, current_user.id)
        return ModifyItineraryResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/{trip_id}/activities/{activity_id}/alternatives", response_model=AlternativesResponse)
async def get_alternatives(
    trip_id: str,
    activity_id: str,
    payload: AlternativesRequest,
    current_user: CurrentUser,
    trip_repo: Annotated[TripRepository, Depends(get_trip_repository)],
    alt_service: Annotated[AlternativeRecommendationService, Depends(get_alternatives_service)],
) -> AlternativesResponse:
    """Get 3 real verified alternative activities for a disliked activity."""
    trip = await trip_repo.get_by_id(trip_id)
    if trip is None or trip.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")

    # Locate the activity
    activity = None
    for day in trip.days:
        if day.get("day_number") == payload.day_number:
            for act in day.get("activities", []):
                if act.get("id") == activity_id or act.get("title", "")[:20] == activity_id[:20]:
                    activity = act
                    break

    if activity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found.")

    try:
        alternatives = await alt_service.get_alternatives(
            activity=activity,
            trip=trip.__dict__,
            user_id=current_user.id,
            limit=3,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return AlternativesResponse(activity_id=activity_id, alternatives=alternatives)


@router.post("/{trip_id}/activities/{activity_id}/replace", response_model=ModifyItineraryResponse)
async def replace_activity(
    trip_id: str,
    activity_id: str,
    payload: ReplaceActivityRequest,
    current_user: CurrentUser,
    trip_repo: Annotated[TripRepository, Depends(get_trip_repository)],
    modifier: Annotated[ItineraryModifier, Depends(get_itinerary_modifier)],
    alt_service: Annotated[AlternativeRecommendationService, Depends(get_alternatives_service)],
) -> ModifyItineraryResponse:
    """Replace an activity with a chosen alternative (by place_id)."""
    trip = await trip_repo.get_by_id(trip_id)
    if trip is None or trip.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")

    # Build new activity data from the chosen alternative
    new_activity = {
        "title": payload.alternative_title,
        "place_id": payload.place_id,
        "category": "attraction",
        "verified": True,
        "place_provider": "google",
    }
    result = await modifier.replace_activity(
        trip, payload.day_number, activity_id, new_activity, current_user.id
    )
    return ModifyItineraryResponse(**result)


@router.post("/{trip_id}/activities/{activity_id}/move", response_model=ModifyItineraryResponse)
async def move_activity(
    trip_id: str,
    activity_id: str,
    payload: MoveActivityRequest,
    current_user: CurrentUser,
    trip_repo: Annotated[TripRepository, Depends(get_trip_repository)],
    modifier: Annotated[ItineraryModifier, Depends(get_itinerary_modifier)],
) -> ModifyItineraryResponse:
    """Move an activity to a different time or day."""
    trip = await trip_repo.get_by_id(trip_id)
    if trip is None or trip.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")
    result = await modifier.move_activity(
        trip, activity_id, payload.from_day, payload.to_day, payload.new_time, current_user.id
    )
    return ModifyItineraryResponse(**result)


@router.delete("/{trip_id}/activities/{activity_id}", response_model=ModifyItineraryResponse)
async def remove_activity(
    trip_id: str,
    activity_id: str,
    day_number: int,
    current_user: CurrentUser,
    trip_repo: Annotated[TripRepository, Depends(get_trip_repository)],
    modifier: Annotated[ItineraryModifier, Depends(get_itinerary_modifier)],
) -> ModifyItineraryResponse:
    """Remove an activity from the itinerary."""
    trip = await trip_repo.get_by_id(trip_id)
    if trip is None or trip.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")
    result = await modifier.remove_activity(trip, day_number, activity_id, current_user.id)
    return ModifyItineraryResponse(**result)


@router.post("/{trip_id}/activities/reorder", response_model=ModifyItineraryResponse)
async def reorder_activities(
    trip_id: str,
    payload: ReorderRequest,
    current_user: CurrentUser,
    trip_repo: Annotated[TripRepository, Depends(get_trip_repository)],
    modifier: Annotated[ItineraryModifier, Depends(get_itinerary_modifier)],
) -> ModifyItineraryResponse:
    """Reorder activities within a day (e.g., after drag-and-drop)."""
    trip = await trip_repo.get_by_id(trip_id)
    if trip is None or trip.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found.")
    result = await modifier.reorder_activities(
        trip, payload.day_number, payload.ordered_activity_ids, current_user.id
    )
    return ModifyItineraryResponse(**result)
