"""
Tests for the ItineraryModifier service.

Tests schedule validation, activity removal, movement, reordering,
and intent parsing with mocked LLMService.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.itinerary_modifier import ItineraryModifier
from app.models.trip import Trip


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_trip(**kwargs) -> Trip:
    defaults = dict(
        id="trip-1",
        user_id="user-1",
        destination="Paris",
        start_date="2025-01-01",
        end_date="2025-01-03",
        budget=1000.0,
        currency="USD",
        travel_style="balanced",
        days=[
            {
                "day_number": 1,
                "title": "Day 1",
                "activities": [
                    {"id": "act-1", "title": "Eiffel Tower", "time": "09:00", "category": "attraction", "estimated_cost": 25.0, "duration_minutes": 120},
                    {"id": "act-2", "title": "Lunch at Café", "time": "12:00", "category": "meal", "estimated_cost": 30.0, "duration_minutes": 60},
                    {"id": "act-3", "title": "Louvre Museum", "time": "14:00", "category": "museum", "estimated_cost": 20.0, "duration_minutes": 180},
                ],
            },
            {
                "day_number": 2,
                "title": "Day 2",
                "activities": [
                    {"id": "act-4", "title": "Notre Dame", "time": "10:00", "category": "culture", "estimated_cost": 0.0, "duration_minutes": 90},
                ],
            },
        ],
        estimated_total_cost=500.0,
        is_saved=False,
    )
    defaults.update(kwargs)
    return Trip(**defaults)


@pytest.fixture
def mock_trip_repo():
    repo = MagicMock()
    repo.update_days = AsyncMock()
    repo.get_by_id = AsyncMock()
    return repo


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.generate_json = AsyncMock()
    return llm


@pytest.fixture
def modifier(mock_trip_repo, mock_llm):
    return ItineraryModifier(mock_trip_repo, mock_llm)


# ---------------------------------------------------------------------------
# Schedule validation tests
# ---------------------------------------------------------------------------

def test_validate_schedule_no_conflict(modifier):
    activities = [
        {"id": "a", "title": "A", "time": "09:00", "duration_minutes": 60},
        {"id": "b", "title": "B", "time": "11:00", "duration_minutes": 60},
    ]
    result = modifier.validate_schedule(activities)
    assert result is None


def test_validate_schedule_with_overlap(modifier):
    activities = [
        {"id": "a", "title": "Morning Tour", "time": "09:00", "duration_minutes": 180},
        {"id": "b", "title": "Early Lunch", "time": "10:00", "duration_minutes": 60},
    ]
    result = modifier.validate_schedule(activities)
    assert result is not None
    assert "Morning Tour" in result
    assert "Early Lunch" in result


def test_validate_schedule_empty(modifier):
    assert modifier.validate_schedule([]) is None


def test_validate_schedule_single_activity(modifier):
    activities = [{"id": "a", "title": "A", "time": "09:00", "duration_minutes": 120}]
    assert modifier.validate_schedule(activities) is None


# ---------------------------------------------------------------------------
# Remove activity tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_remove_activity_success(modifier, mock_trip_repo):
    trip = make_trip()
    result = await modifier.remove_activity(trip, 1, "act-1", "user-1")
    assert result["success"] is True
    assert "Eiffel Tower" in result["message"]
    mock_trip_repo.update_days.assert_called_once()
    updated_days = mock_trip_repo.update_days.call_args[0][1]
    day1_activities = updated_days[0]["activities"]
    assert len(day1_activities) == 2
    assert all(a["id"] != "act-1" for a in day1_activities)


@pytest.mark.asyncio
async def test_remove_activity_not_found(modifier, mock_trip_repo):
    trip = make_trip()
    result = await modifier.remove_activity(trip, 1, "nonexistent-id", "user-1")
    assert result["success"] is False
    mock_trip_repo.update_days.assert_not_called()


@pytest.mark.asyncio
async def test_remove_activity_wrong_day(modifier, mock_trip_repo):
    trip = make_trip()
    result = await modifier.remove_activity(trip, 99, "act-1", "user-1")
    assert result["success"] is False
    mock_trip_repo.update_days.assert_not_called()


# ---------------------------------------------------------------------------
# Move activity tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_move_activity_between_days(modifier, mock_trip_repo):
    trip = make_trip()
    result = await modifier.move_activity(trip, "act-1", 1, 2, "11:00", "user-1")
    assert result["success"] is True
    assert "Day 2" in result["message"]
    updated_days = mock_trip_repo.update_days.call_args[0][1]
    # Source day should have 2 activities now
    assert len(updated_days[0]["activities"]) == 2
    # Target day should have 2 activities now
    assert len(updated_days[1]["activities"]) == 2
    # The moved activity should have the new time
    moved = next(a for a in updated_days[1]["activities"] if a["title"] == "Eiffel Tower")
    assert moved["time"] == "11:00"


@pytest.mark.asyncio
async def test_move_activity_invalid_source_day(modifier, mock_trip_repo):
    trip = make_trip()
    result = await modifier.move_activity(trip, "act-1", 99, 2, "11:00", "user-1")
    assert result["success"] is False
    mock_trip_repo.update_days.assert_not_called()


# ---------------------------------------------------------------------------
# Reorder tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reorder_activities(modifier, mock_trip_repo):
    trip = make_trip()
    # Reverse the order
    result = await modifier.reorder_activities(trip, 1, ["act-3", "act-2", "act-1"], "user-1")
    assert result["success"] is True
    updated_days = mock_trip_repo.update_days.call_args[0][1]
    day1_acts = updated_days[0]["activities"]
    assert day1_acts[0]["id"] == "act-3"
    assert day1_acts[1]["id"] == "act-2"
    assert day1_acts[2]["id"] == "act-1"


@pytest.mark.asyncio
async def test_reorder_preserves_unlisted_activities(modifier, mock_trip_repo):
    """Activities not in the ordered list should still appear at the end."""
    trip = make_trip()
    result = await modifier.reorder_activities(trip, 1, ["act-2"], "user-1")
    assert result["success"] is True
    updated_days = mock_trip_repo.update_days.call_args[0][1]
    day1_acts = updated_days[0]["activities"]
    assert len(day1_acts) == 3
    assert day1_acts[0]["id"] == "act-2"  # first as specified


# ---------------------------------------------------------------------------
# Replace activity tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_replace_activity_success(modifier, mock_trip_repo):
    trip = make_trip()
    new_data = {"title": "Arc de Triomphe", "category": "attraction", "estimated_cost": 15.0}
    result = await modifier.replace_activity(trip, 1, "act-1", new_data, "user-1")
    assert result["success"] is True
    assert "Arc de Triomphe" in result["message"]
    updated_days = mock_trip_repo.update_days.call_args[0][1]
    day1_acts = updated_days[0]["activities"]
    titles = [a["title"] for a in day1_acts]
    assert "Arc de Triomphe" in titles
    assert "Eiffel Tower" not in titles


@pytest.mark.asyncio
async def test_replace_activity_inherits_time(modifier, mock_trip_repo):
    """Replacement activity should keep the original's time slot."""
    trip = make_trip()
    new_data = {"title": "New Place", "category": "attraction"}
    result = await modifier.replace_activity(trip, 1, "act-1", new_data, "user-1")
    assert result["success"] is True
    updated_days = mock_trip_repo.update_days.call_args[0][1]
    day1_acts = updated_days[0]["activities"]
    replaced = next(a for a in day1_acts if a["title"] == "New Place")
    assert replaced["time"] == "09:00"  # inherited from act-1


# ---------------------------------------------------------------------------
# Intent parsing tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_modify_by_intent_remove(modifier, mock_trip_repo, mock_llm):
    trip = make_trip()
    mock_llm.generate_json.return_value = {
        "action": "remove_activity",
        "target_activity_id": "act-2",
        "target_activity_title": "Lunch at Café",
        "target_day": 1,
        "constraints": {},
        "explanation": "Removing the lunch activity as requested.",
    }
    result = await modifier.modify_by_intent(trip, "Remove the lunch", "user-1")
    assert result["success"] is True
    mock_trip_repo.update_days.assert_called_once()


@pytest.mark.asyncio
async def test_modify_by_intent_unknown(modifier, mock_trip_repo, mock_llm):
    trip = make_trip()
    mock_llm.generate_json.return_value = {
        "action": "unknown",
        "explanation": "Could not parse intent.",
    }
    result = await modifier.modify_by_intent(trip, "zzz", "user-1")
    assert result["success"] is False
    mock_trip_repo.update_days.assert_not_called()


@pytest.mark.asyncio
async def test_modify_by_intent_llm_failure(modifier, mock_trip_repo, mock_llm):
    """If LLM throws, should return success=False gracefully."""
    trip = make_trip()
    mock_llm.generate_json.side_effect = RuntimeError("LLM timeout")
    result = await modifier.modify_by_intent(trip, "Remove the museum", "user-1")
    assert result["success"] is False


# ---------------------------------------------------------------------------
# Time parsing tests
# ---------------------------------------------------------------------------

def test_parse_time_24h(modifier):
    assert ItineraryModifier._parse_time("09:00") == 540  # 9*60
    assert ItineraryModifier._parse_time("14:30") == 870


def test_parse_time_12h(modifier):
    assert ItineraryModifier._parse_time("09:00 AM") == 540
    assert ItineraryModifier._parse_time("02:30 PM") == 870


def test_parse_time_invalid(modifier):
    assert ItineraryModifier._parse_time("") == 0
    assert ItineraryModifier._parse_time("invalid") == 0
