from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, get_user_repository
from app.repositories.user_repository import UserRepository
from app.schemas.profile import (
    ProfileResponse,
    SyncProfileRequest,
    UpdateProfileRequest,
    UserPreferencesSchema,
)

router = APIRouter(prefix="/profile", tags=["Profile"])


def _to_response(user) -> ProfileResponse:
    return ProfileResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_email_verified=user.is_email_verified,
        preferences=UserPreferencesSchema(**user.preferences.to_dict()),
    )


@router.post("/sync", response_model=ProfileResponse)
async def sync_profile(
    payload: SyncProfileRequest,
    current_user: CurrentUser,
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> ProfileResponse:
    """
    Called once by the frontend immediately after Firebase signup/login.
    `CurrentUser` already lazily created the Firestore doc if it didn't
    exist; this just applies the display name from the signup form, since
    that may not yet be reflected in the Firebase Auth token's `name` claim.
    """
    if payload.full_name and payload.full_name != current_user.full_name:
        current_user = await user_repository.update_profile(current_user.id, full_name=payload.full_name)
    return _to_response(current_user)


@router.get("", response_model=ProfileResponse)
async def get_profile(current_user: CurrentUser) -> ProfileResponse:
    return _to_response(current_user)


@router.put("", response_model=ProfileResponse)
async def update_profile(
    payload: UpdateProfileRequest,
    current_user: CurrentUser,
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> ProfileResponse:
    if payload.full_name:
        current_user = await user_repository.update_profile(current_user.id, full_name=payload.full_name)
    return _to_response(current_user)


@router.put("/preferences", response_model=ProfileResponse)
async def update_preferences(
    payload: UserPreferencesSchema,
    current_user: CurrentUser,
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> ProfileResponse:
    updated_user = await user_repository.update_preferences(current_user.id, payload.model_dump())
    return _to_response(updated_user)
