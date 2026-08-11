import pytest
from app.integrations.weather_service import get_weather_service
from app.integrations.navigation_service import get_navigation_service
from app.integrations.opentripmap_service import get_opentripmap_service
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
    v1 = [0.1] * 768
    v2 = [0.9] * 768
    store.add_vectors([v1, v2], [{"id": 1}, {"id": 2}])
    
    results = store.search([0.1] * 768, top_k=1)
    assert len(results) == 1
    assert results[0]["id"] == 1
