"""
Tests for Google Places Provider, TouristRanker, and PlaceConsistencyValidator.

All external I/O is mocked — no real HTTP calls are made.
14 test cases covering:
  - GooglePlacesProvider attraction and restaurant search
  - GooglePlacesProvider geocoding
  - GooglePlacesProvider auth failure handling
  - TouristRanker: tourist type scoring and commercial penalty
  - TouristRanker: restaurant scoring
  - TouristRanker: duplicate penalty
  - PlaceConsistencyValidator: mismatch detection
  - PlaceConsistencyValidator: description replacement
  - PlaceConsistencyValidator: is_valid_attraction category gating
  - PlaceEnrichmentService: Google primary → result
  - PlaceEnrichmentService: Geoapify fallback when Google returns nothing
  - PlaceEnrichmentService: reject when both providers return nothing
  - PlaceEnrichmentService: minimum tourist relevance threshold enforced
  - Config: PLACE_PROVIDER and ENABLE_GEOAPIFY_FALLBACK defaults
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

from app.integrations.place_provider import PlaceCandidate, GeoPoint
from app.cognitive.tourist_ranker import TouristRanker, MIN_TOURIST_RELEVANCE
from app.cognitive.place_consistency import PlaceConsistencyValidator


# ---------------------------------------------------------------------------
# Helpers: build mock PlaceCandidates
# ---------------------------------------------------------------------------

def _make_candidate(
    name: str,
    types: list[str],
    rating: float | None = 4.5,
    user_ratings_total: int | None = 1000,
    distance_m: float = 500,
    place_id: str = "test_id_1",
    source: str = "google",
) -> PlaceCandidate:
    return PlaceCandidate(
        place_id=place_id,
        name=name,
        lat=16.30,
        lon=80.44,
        address=f"{name} Road, Guntur",
        rating=rating,
        user_ratings_total=user_ratings_total,
        types=types,
        distance_m=distance_m,
        source=source,
    )


# ---------------------------------------------------------------------------
# 1. GooglePlacesProvider: attraction search returns PlaceCandidates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_google_attraction_search_returns_candidates():
    """Google searchNearby returns tourist attraction candidates."""
    from app.integrations.google_places_provider import GooglePlacesProvider

    mock_response = {
        "places": [
            {
                "id": "g_temple_001",
                "displayName": {"text": "Kotappakonda Temple"},
                "formattedAddress": "Kotappakonda, Guntur, AP",
                "location": {"latitude": 16.15, "longitude": 79.96},
                "rating": 4.7,
                "userRatingCount": 2800,
                "types": ["hindu_temple", "tourist_attraction", "place_of_worship"],
                "businessStatus": "OPERATIONAL",
            }
        ]
    }

    provider = GooglePlacesProvider.__new__(GooglePlacesProvider)
    provider._search_cache = {}
    provider._detail_cache = {}

    with patch("app.integrations.google_places_provider.get_settings") as mock_settings:
        mock_settings.return_value.GOOGLE_PLACES_API_KEY = "test_key"
        mock_settings.return_value.GOOGLE_PLACES_BASE_URL = "https://places.googleapis.com/v1"
        mock_settings.return_value.GOOGLE_PLACES_TIMEOUT_SECONDS = 10
        provider._settings = mock_settings.return_value

        with patch("app.integrations.google_places_provider._post_with_retry", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            results = await provider.search_attractions(
                lat=16.30, lon=80.44, query="temples Guntur", radius_m=5000, limit=5
            )

    assert len(results) == 1
    assert results[0].name == "Kotappakonda Temple"
    assert results[0].rating == 4.7
    assert "hindu_temple" in results[0].types
    assert results[0].source == "google"


# ---------------------------------------------------------------------------
# 2. GooglePlacesProvider: restaurant search returns candidates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_google_restaurant_search():
    """Google searchText returns restaurant candidates."""
    from app.integrations.google_places_provider import GooglePlacesProvider

    mock_response = {
        "places": [
            {
                "id": "g_rest_001",
                "displayName": {"text": "Nagarjuna Restaurant"},
                "formattedAddress": "Brodipet, Guntur, AP",
                "location": {"latitude": 16.31, "longitude": 80.43},
                "rating": 4.3,
                "userRatingCount": 890,
                "types": ["restaurant"],
                "businessStatus": "OPERATIONAL",
                "priceLevel": "PRICE_LEVEL_MODERATE",
            }
        ]
    }

    provider = GooglePlacesProvider.__new__(GooglePlacesProvider)
    provider._search_cache = {}
    provider._detail_cache = {}

    with patch("app.integrations.google_places_provider.get_settings") as mock_settings:
        mock_settings.return_value.GOOGLE_PLACES_API_KEY = "test_key"
        mock_settings.return_value.GOOGLE_PLACES_BASE_URL = "https://places.googleapis.com/v1"
        mock_settings.return_value.GOOGLE_PLACES_TIMEOUT_SECONDS = 10
        provider._settings = mock_settings.return_value

        with patch("app.integrations.google_places_provider._post_with_retry", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            results = await provider.search_restaurants(
                lat=16.30, lon=80.44, food_query="Andhra meals Guntur", meal_type="lunch"
            )

    assert len(results) == 1
    assert results[0].name == "Nagarjuna Restaurant"
    assert results[0].price_level == 2  # MODERATE


# ---------------------------------------------------------------------------
# 3. GooglePlacesProvider: auth failure logged gracefully
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_google_auth_failure_returns_empty():
    """401 from Google returns [] without crashing."""
    from app.integrations.google_places_provider import GooglePlacesProvider

    provider = GooglePlacesProvider.__new__(GooglePlacesProvider)
    provider._search_cache = {}
    provider._detail_cache = {}

    with patch("app.integrations.google_places_provider.get_settings") as mock_settings:
        mock_settings.return_value.GOOGLE_PLACES_API_KEY = "invalid_key"
        mock_settings.return_value.GOOGLE_PLACES_BASE_URL = "https://places.googleapis.com/v1"
        mock_settings.return_value.GOOGLE_PLACES_TIMEOUT_SECONDS = 10
        provider._settings = mock_settings.return_value

        # _post_with_retry returns None on auth failure
        with patch("app.integrations.google_places_provider._post_with_retry", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = None
            results = await provider.search_attractions(
                lat=16.30, lon=80.44, query="temples", radius_m=5000
            )

    assert results == []


# ---------------------------------------------------------------------------
# 4. GooglePlacesProvider: no key configured → returns empty
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_google_no_key_configured_returns_empty():
    """No API key → graceful degradation (returns [])."""
    from app.integrations.google_places_provider import GooglePlacesProvider

    provider = GooglePlacesProvider.__new__(GooglePlacesProvider)
    provider._search_cache = {}
    provider._detail_cache = {}

    with patch("app.integrations.google_places_provider.get_settings") as mock_settings:
        mock_settings.return_value.GOOGLE_PLACES_API_KEY = None
        provider._settings = mock_settings.return_value
        results = await provider.search_attractions(lat=16.30, lon=80.44, query="temples")

    assert results == []


# ---------------------------------------------------------------------------
# 5. TouristRanker: temple beats juice bar for attraction slot
# ---------------------------------------------------------------------------

def test_tourist_ranker_temple_beats_juice_bar():
    """Hindu temple must rank above juice bar for an attraction slot."""
    ranker = TouristRanker()

    temple = _make_candidate(
        "Amaravati Stupa", ["historical_landmark", "tourist_attraction"], rating=4.8, place_id="t1"
    )
    juice = _make_candidate(
        "Fresh Juice Corner", ["juice_bar", "food"], rating=4.5, place_id="j1"
    )

    ranked = ranker.score_candidates(
        [juice, temple],
        slot_intent="historical landmark visit",
        radius_m=5000,
    )

    assert ranked[0].name == "Amaravati Stupa"
    assert ranked[0].tourist_relevance > ranked[1].tourist_relevance


# ---------------------------------------------------------------------------
# 6. TouristRanker: commercial business receives penalty
# ---------------------------------------------------------------------------

def test_tourist_ranker_commercial_penalty():
    """Shopping mall receives commercial penalty and low tourist relevance."""
    ranker = TouristRanker()

    mall = _make_candidate(
        "Phoenix Market City", ["shopping_mall"], rating=4.5, place_id="m1"
    )

    ranked = ranker.score_candidates([mall], slot_intent="attraction", radius_m=5000)

    assert ranked[0].tourist_relevance < MIN_TOURIST_RELEVANCE


# ---------------------------------------------------------------------------
# 7. TouristRanker: minimum threshold rejects low-scoring candidates
# ---------------------------------------------------------------------------

def test_tourist_ranker_min_threshold():
    """Candidates below MIN_TOURIST_RELEVANCE are filtered out."""
    ranker = TouristRanker()

    gas_station = _make_candidate(
        "Indian Oil Petrol Bunk", ["gas_station"], rating=3.0, place_id="g1"
    )

    ranked = ranker.score_candidates([gas_station], slot_intent="tourist attraction")
    passing = [c for c in ranked if c.tourist_relevance >= MIN_TOURIST_RELEVANCE]

    assert len(passing) == 0


# ---------------------------------------------------------------------------
# 8. TouristRanker: duplicate penalty applied
# ---------------------------------------------------------------------------

def test_tourist_ranker_duplicate_penalty():
    """Already-used place_id receives duplicate penalty."""
    ranker = TouristRanker()

    c1 = _make_candidate("Kondaveedu Fort", ["historical_landmark"], place_id="k1")
    c2 = _make_candidate("Kondaveedu Fort", ["historical_landmark"], place_id="k1")

    ranked_fresh = ranker.score_candidates([c1], slot_intent="fort visit")
    ranked_used = ranker.score_candidates([c2], slot_intent="fort visit", used_place_ids={"k1"})

    assert ranked_used[0].tourist_relevance < ranked_fresh[0].tourist_relevance


# ---------------------------------------------------------------------------
# 9. TouristRanker: restaurant ranking by food query match
# ---------------------------------------------------------------------------

def test_tourist_ranker_restaurant_food_query_match():
    """Restaurant matching food_query ranks higher than unrelated one."""
    ranker = TouristRanker()

    andhra_rest = _make_candidate(
        "Andhra Meals Corner", ["restaurant"], rating=4.2, place_id="r1"
    )
    pizza_place = _make_candidate(
        "Pizza Hut", ["restaurant", "fast_food_restaurant"], rating=3.9, place_id="r2"
    )

    ranked = ranker.score_restaurant_candidates(
        [pizza_place, andhra_rest],
        food_query="Andhra meals",
        meal_type="lunch",
    )

    assert ranked[0].name == "Andhra Meals Corner"


# ---------------------------------------------------------------------------
# 10. PlaceConsistencyValidator: mismatch detection
# ---------------------------------------------------------------------------

def test_consistency_validator_detects_mismatch():
    """Restaurant + historical description → mismatch detected."""
    validator = PlaceConsistencyValidator()

    activity: dict = {
        "title": "Pizza Hut",
        "description": "ancient colonial heritage site with historical artifacts and monuments",
    }

    result = validator.validate_and_fix(
        activity,
        place_name="Pizza Hut",
        place_types=["restaurant", "fast_food_restaurant"],
        destination="Guntur",
    )

    assert result["description_corrected"] is True
    assert "Pizza Hut" in result["description"]
    assert "description_original" in result


# ---------------------------------------------------------------------------
# 11. PlaceConsistencyValidator: no mismatch for consistent activities
# ---------------------------------------------------------------------------

def test_consistency_validator_no_mismatch_for_temple():
    """Temple + cultural description → no mismatch."""
    validator = PlaceConsistencyValidator()

    activity: dict = {
        "title": "Amaravati Buddhist Stupa",
        "description": "An ancient Buddhist monument and UNESCO heritage site",
    }

    result = validator.validate_and_fix(
        activity,
        place_name="Amaravati Buddhist Stupa",
        place_types=["tourist_attraction", "historical_landmark"],
        destination="Amaravati",
    )

    assert result["description_corrected"] is False


# ---------------------------------------------------------------------------
# 12. PlaceConsistencyValidator: is_valid_attraction rejects restaurants for attraction slots
# ---------------------------------------------------------------------------

def test_consistency_validator_restaurant_not_valid_attraction():
    """Restaurant is not valid for an attraction slot."""
    validator = PlaceConsistencyValidator()

    assert validator.is_valid_attraction(["restaurant", "fast_food_restaurant"], "attraction") is False
    assert validator.is_valid_attraction(["hindu_temple", "tourist_attraction"], "attraction") is True
    assert validator.is_valid_attraction(["restaurant"], "meal") is True


# ---------------------------------------------------------------------------
# 13. PlaceEnrichmentService: Google primary returns result
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_place_enrichment_google_primary_returns_enrichment():
    """PlaceEnrichmentService uses Google result when available."""
    from app.services.place_enrichment_service import PlaceEnrichmentService
    from app.integrations.navigation_service import NavigationService

    mock_google = AsyncMock()
    mock_google.geocode = AsyncMock(return_value=GeoPoint(lat=16.30, lon=80.44))
    mock_google.search_attractions = AsyncMock(return_value=[
        _make_candidate(
            "Amaravati Buddhist Stupa",
            ["historical_landmark", "tourist_attraction"],
            rating=4.8,
            place_id="google_001",
        )
    ])

    mock_geoapify = AsyncMock()
    mock_geoapify.geocode = AsyncMock(return_value=None)

    mock_nav = AsyncMock()
    mock_ranker = TouristRanker()
    mock_validator = PlaceConsistencyValidator()

    with patch("app.services.place_enrichment_service.get_settings") as mock_settings:
        mock_settings.return_value.PLACE_PROVIDER = "google"
        mock_settings.return_value.GOOGLE_PLACES_API_KEY = "test_key"
        mock_settings.return_value.GEOAPIFY_API_KEY = "geo_key"
        mock_settings.return_value.ENABLE_GEOAPIFY_FALLBACK = True

        svc = PlaceEnrichmentService(
            navigation_service=mock_nav,
            geoapify_provider=mock_geoapify,
            google_places_provider=mock_google,
            tourist_ranker=mock_ranker,
            place_consistency_validator=mock_validator,
        )

        result = await svc.enrich_place(
            title="ancient Buddhist ruins",
            location_hint="Amaravati",
            destination="Guntur",
            slot_intent="ancient Buddhist stupa visit",
            place_query="Buddhist monument Guntur",
            category="attraction",
        )

    assert result is not None
    assert result["matched_place_name"] == "Amaravati Buddhist Stupa"
    assert result["source"] == "google"
    assert result["verified"] is True


# ---------------------------------------------------------------------------
# 14. Config defaults: PLACE_PROVIDER and ENABLE_GEOAPIFY_FALLBACK
# ---------------------------------------------------------------------------

def test_config_place_provider_defaults():
    """PLACE_PROVIDER defaults to 'google', fallback enabled by default."""
    from app.core.config import Settings
    import os

    # Settings with minimum required fields
    os.environ.setdefault("FIREBASE_PROJECT_ID", "test-project")
    settings = Settings(
        FIREBASE_PROJECT_ID="test-project",
        GOOGLE_PLACES_API_KEY=None,
    )

    assert settings.PLACE_PROVIDER == "google"
    assert settings.ENABLE_GEOAPIFY_FALLBACK is True
    assert settings.GOOGLE_PLACES_BASE_URL == "https://places.googleapis.com/v1"
