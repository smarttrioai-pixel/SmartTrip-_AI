from pydantic import BaseModel, Field


class UserPreferencesSchema(BaseModel):
    budget: float | None = None
    currency: str = "USD"
    language: str = "en"
    travel_style: str = "balanced"
    food_preference: str = "no_preference"
    accommodation: str = "hotel"
    transport: str = "any"
    accessibility_needs: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)


class SyncProfileRequest(BaseModel):
    """Sent once right after client-side Firebase signup/login to make sure
    the Firestore profile reflects the display name the user just chose
    (the lazy-create in get_current_user covers the fallback case, but this
    lets the frontend set it explicitly and immediately)."""
    full_name: str | None = Field(default=None, min_length=2, max_length=255)


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)


class ProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    is_email_verified: bool
    preferences: UserPreferencesSchema
