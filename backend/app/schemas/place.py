from pydantic import BaseModel, Field


class PlaceEnrichmentRequest(BaseModel):
    title: str
    location_hint: str = ""
    destination: str
    category: str | None = None
    meal_type: str | None = None
    food_query: str | None = None


class BatchEnrichRequest(BaseModel):
    destination: str
    places: list[PlaceEnrichmentRequest] = Field(..., max_length=40)


class PlaceEnrichmentResult(BaseModel):
    matched_place_name: str | None = None
    image_url: str | None = None
    rating: float | None = None
    rating_scale: str | None = None
    reviews_count: int | None = None
    reviews_count_note: str | None = None
    category: str | None = None
    address: str | None = None
    opening_hours: str | None = None
    opening_hours_note: str | None = None
    estimated_ticket_price: float | None = None
    estimated_ticket_price_note: str | None = None
    lat: float | None = None
    lon: float | None = None
    wikipedia_summary: str | None = None
    found: bool = True
    # Source provenance — added for Geoapify migration.
    # Optional / None-defaulted for backward compatibility with existing
    # Firestore saved-trip documents that pre-date this field.
    source: str | None = None
    source_id: str | None = None


class BatchEnrichResponse(BaseModel):
    results: list[PlaceEnrichmentResult] = Field(default_factory=list)
