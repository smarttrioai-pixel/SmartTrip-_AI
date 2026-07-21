from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, get_trip_planner_service
from app.schemas.trip import GenerateItineraryRequest, SaveTripRequest, TripResponse
from app.services.trip_service import TripPlannerService

router = APIRouter(prefix="/trips", tags=["AI Trip Planner"])


@router.post("/generate", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
async def generate_itinerary(
    payload: GenerateItineraryRequest,
    current_user: CurrentUser,
    trip_service: Annotated[TripPlannerService, Depends(get_trip_planner_service)],
) -> TripResponse:
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_date must be on or after start_date")
    try:
        return await trip_service.generate_itinerary(current_user.id, payload)
    except RuntimeError as exc:
        # Raised by app.core.gemini when GEMINI_API_KEY isn't configured.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("", response_model=list[TripResponse])
async def list_trips(
    current_user: CurrentUser,
    trip_service: Annotated[TripPlannerService, Depends(get_trip_planner_service)],
    saved_only: bool = False,
) -> list[TripResponse]:
    return await trip_service.list_trips(current_user.id, saved_only=saved_only)


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
