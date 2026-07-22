import pytest
from app.agents.multi_agent_graph import get_multi_agent_graph

@pytest.mark.asyncio
async def test_multi_agent_graph_execution():
    graph = get_multi_agent_graph()
    initial_state = {
        "user_id": "test_user_1",
        "destination": "Rome",
        "start_date": "2026-08-01",
        "end_date": "2026-08-05",
        "budget": 1200.0,
        "currency": "EUR",
        "travel_style": "balanced",
        "interests": ["Architecture", "History", "Food"],
    }
    
    result = await graph.execute_graph(initial_state)
    
    assert "raw_plan" in result
    assert "weather_info" in result
    assert "safety_info" in result
    assert "hotel_recommendations" in result
    assert "restaurant_recommendations" in result
    assert "navigation_route" in result
    assert "final_response" in result
    assert len(result["execution_trace"]) >= 5
