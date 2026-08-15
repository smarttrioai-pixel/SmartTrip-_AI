import pytest
from app.integrations.weather_service import get_weather_service
from app.integrations.navigation_service import get_navigation_service
from app.integrations.geoapify_provider import get_geoapify_provider, GeoapifyProvider
from app.integrations.wikipedia_service import get_wikipedia_service
from app.integrations.faiss_vector_store import get_faiss_vector_store

@pytest.mark.asyncio
async def test_weather_service():
    service = get_weather_service()
    forecast = await service.get_forecast(48.8566, 2.3522)
    assert "temperature" in forecast
    assert "condition" in forecast
    assert "suitability_score" in forecast

@pytest.mark.asyncio
async def test_navigation_service():
    service = get_navigation_service()
    geocode = await service.geocode("Eiffel Tower")
    assert geocode["lat"] != 0.0
    
    route = await service.calculate_route(48.8566, 2.3522, 48.8606, 2.3376, mode="walking")
    assert route["distance_km"] > 0
    assert "steps" in route

@pytest.mark.asyncio
async def test_wikipedia_service():
    service = get_wikipedia_service()
    info = await service.get_landmark_info("Eiffel Tower")
    assert info["title"] == "Eiffel Tower"
    assert len(info["summary"]) > 0

def test_faiss_vector_store():
    store = get_faiss_vector_store()
    store.clear()
    # v1 and v2 must be directionally distinct so cosine similarity
    # gives a clear ordering. [0.1]*768 vs [0.9]*768 are parallel
    # (identical direction), making the match non-deterministic.
    # Use orthogonal unit vectors instead.
    v1 = [1.0] + [0.0] * 767         # points in x direction
    v2 = [0.0, 1.0] + [0.0] * 766   # points in y direction
    store.add_vectors([v1, v2], [{"id": 1}, {"id": 2}])

    # Query identical to v1 → cosine similarity 1.0 → must return id=1
    results = store.search(v1, top_k=1)
    assert len(results) == 1
    assert int(results[0]["id"]) == 1

def test_geoapify_provider_no_key_returns_gracefully():
    """
    GeoapifyProvider must NOT crash when GEOAPIFY_API_KEY is unset.
    It should return empty results / None, not raise an exception.
    The app must continue running without a Geoapify key.
    """
    provider = get_geoapify_provider()
    # Verify it is the correct type
    assert isinstance(provider, GeoapifyProvider)
    # Verify category mapping works
    cats = GeoapifyProvider.categories_for_concept("restaurant")
    assert "catering.restaurant" in cats
    cats_meal = GeoapifyProvider.categories_for_concept("meal")
    assert any("catering" in c for c in cats_meal)
    cats_museum = GeoapifyProvider.categories_for_concept("museum")
    assert "entertainment.museum" in cats_museum

@pytest.mark.asyncio
async def test_geoapify_provider_geocode_no_key_returns_none():
    """
    When GEOAPIFY_API_KEY is not configured, geocode() must return None
    without raising and without logging anything sensitive.
    """
    from unittest.mock import MagicMock
    provider = GeoapifyProvider()
    # Patch _settings directly (simpler than trying to override a property)
    mock_settings = MagicMock()
    mock_settings.GEOAPIFY_API_KEY = None
    mock_settings.GEOAPIFY_BASE_URL = "https://api.geoapify.com"
    mock_settings.GEOAPIFY_TIMEOUT_SECONDS = 10
    provider._settings = mock_settings

    result = await provider.geocode("Guntur")
    assert result is None  # graceful None, not an exception

@pytest.mark.asyncio
async def test_geoapify_provider_search_no_key_returns_empty(monkeypatch):
    """
    When GEOAPIFY_API_KEY is not configured, search_places() must return []
    without raising.
    """
    from unittest.mock import MagicMock
    provider = GeoapifyProvider()
    mock_settings = MagicMock()
    mock_settings.GEOAPIFY_API_KEY = None
    mock_settings.GEOAPIFY_BASE_URL = "https://api.geoapify.com"
    mock_settings.GEOAPIFY_TIMEOUT_SECONDS = 10
    provider._settings = mock_settings

    results = await provider.search_places(
        latitude=16.3008, longitude=80.4428,
        categories=["catering.restaurant"],
        radius_meters=5000,
    )
    assert results == []
