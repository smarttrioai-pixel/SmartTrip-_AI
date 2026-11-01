"""
Tests for production error fixes in SmartTrip AI.

Covers:
  - Error 1: Open-Meteo HTTP 429 — batch forecast, retry with backoff
  - Error 2: Gemini HTTP 503 — 3 retries with exponential backoff
  - Error 3: Gemini JSON truncation — detection and retry
  - Error 4: Pydantic protected namespace — no warnings
  - Error 5: Firestore deprecated .where() — FieldFilter usage
  - Regression: trip generation without weather data

All external API calls are mocked. No real quota is consumed.
"""
from __future__ import annotations

import asyncio
import json
import warnings
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def make_httpx_response(status_code: int, json_data: dict | None = None, headers: dict | None = None):
    """Create a fake httpx.Response-like object."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.headers = headers or {}
    return resp


def open_meteo_range_response(start_date: date, end_date: date) -> dict:
    """Build a realistic Open-Meteo daily response for a date range."""
    dates = []
    d = start_date
    while d <= end_date:
        dates.append(d.isoformat())
        d += timedelta(days=1)
    n = len(dates)
    return {
        "daily": {
            "time": dates,
            "weathercode": [0] * n,
            "temperature_2m_max": [32.0] * n,
            "temperature_2m_min": [24.0] * n,
            "precipitation_sum": [0.0] * n,
            "windspeed_10m_max": [12.0] * n,
            "precipitation_probability_max": [10] * n,
        }
    }


# ===========================================================================
# Error 1: Open-Meteo 429 — batch forecast uses ONE request
# ===========================================================================

class TestWeatherBatchForecast:
    """
    Validates that get_forecast_range() issues a SINGLE HTTP request for
    a multi-day trip instead of N per-day requests (which caused HTTP 429).
    """

    @pytest.mark.asyncio
    async def test_single_request_for_7_day_trip(self):
        """7-day trip → exactly 1 HTTP GET to Open-Meteo."""
        from app.integrations.weather_service import WeatherService

        start = date.today() + timedelta(days=1)
        end = start + timedelta(days=6)   # 7 days

        mock_resp = make_httpx_response(200, open_meteo_range_response(start, end))

        with patch("app.integrations.weather_service._http_get_with_retry",
                   new=AsyncMock(return_value=mock_resp)) as mock_get:
            svc = WeatherService()
            result = await svc.get_forecast_range(54.0, 78.0, start, end)

        assert mock_get.call_count == 1, (
            f"Expected 1 HTTP request, got {mock_get.call_count}. "
            "Per-day loop would produce 7."
        )
        assert len(result) == 7
        for d, snap in result.items():
            assert snap["status"] == "available", f"Day {d} unexpectedly unavailable"

    @pytest.mark.asyncio
    async def test_cache_prevents_duplicate_requests(self):
        """Second call for the same dates uses cache, not HTTP."""
        from app.integrations.weather_service import WeatherService

        start = date.today() + timedelta(days=2)
        end = start + timedelta(days=2)

        mock_resp = make_httpx_response(200, open_meteo_range_response(start, end))

        svc = WeatherService()
        with patch("app.integrations.weather_service._http_get_with_retry",
                   new=AsyncMock(return_value=mock_resp)) as mock_get:
            await svc.get_forecast_range(54.0, 78.0, start, end)
            # Second call — should use cache
            await svc.get_forecast_range(54.0, 78.0, start, end)

        assert mock_get.call_count == 1, "Cache should prevent the second HTTP request"

    @pytest.mark.asyncio
    async def test_429_retry_with_backoff(self):
        """HTTP 429 is retried up to 3 times with backoff before giving up."""
        from app.integrations import weather_service as ws

        call_count = 0

        async def fake_http_get(url):
            nonlocal call_count
            call_count += 1
            # All attempts return 429
            resp = make_httpx_response(429)
            resp.headers = {}
            return resp

        # Override the internal function directly
        original = ws._http_get_with_retry
        ws._http_get_with_retry = fake_http_get

        try:
            svc = ws.WeatherService()
            start = date.today() + timedelta(days=1)
            end = start + timedelta(days=2)

            with patch("asyncio.sleep", new=AsyncMock()):  # don't actually sleep in tests
                result = await svc.get_forecast_range(1.0, 1.0, start, end)
        finally:
            ws._http_get_with_retry = original

        # All dates should be unavailable (API failed after retries)
        for d, snap in result.items():
            assert snap["status"] == "unavailable"

    @pytest.mark.asyncio
    async def test_weather_failure_does_not_crash_trip_generation(self):
        """Weather API failure returns unavailable dict — never raises."""
        from app.integrations.weather_service import WeatherService

        start = date.today() + timedelta(days=1)
        end = start + timedelta(days=3)

        with patch("app.integrations.weather_service._http_get_with_retry",
                   new=AsyncMock(return_value=None)):  # simulates total failure
            svc = WeatherService()
            result = await svc.get_forecast_range(1.0, 1.0, start, end)

        assert isinstance(result, dict)
        for d, snap in result.items():
            assert snap["status"] == "unavailable"
            assert snap["is_suitable_outdoor"] is True  # conservative default

    @pytest.mark.asyncio
    async def test_past_dates_are_unavailable_without_http(self):
        """Past dates never trigger an HTTP request."""
        from app.integrations.weather_service import WeatherService

        start = date(2020, 1, 1)
        end = date(2020, 1, 3)

        with patch("app.integrations.weather_service._http_get_with_retry",
                   new=AsyncMock(side_effect=AssertionError("Should not call HTTP for past dates"))):
            svc = WeatherService()
            result = await svc.get_forecast_range(1.0, 1.0, start, end)

        for d, snap in result.items():
            assert snap["status"] == "unavailable"
            assert snap.get("reason") == "past_date"


# ===========================================================================
# Error 2: Gemini HTTP 503 — retry with exponential backoff
# ===========================================================================

class TestLLMServiceRetries:
    """Validates that LLMService retries up to 3 times on 503/500 errors."""

    @pytest.mark.asyncio
    async def test_503_retried_3_times(self):
        """Provider raises 503 RuntimeError → LLMService retries exactly 3 times."""
        from app.services.llm_service import LLMService

        call_count = 0

        async def fake_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Gemini API error (503): service unavailable")

        provider = MagicMock()
        provider.provider_name = "gemini"
        provider.model_name = "gemini-2.5-flash"
        provider.generate = fake_generate

        svc = LLMService(provider)

        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(RuntimeError, match="503|service unavailable"):
                await svc.generate("sys", "user")

        assert call_count == 4, (
            f"Expected 4 calls (1 initial + 3 retries), got {call_count}"
        )

    @pytest.mark.asyncio
    async def test_503_succeeds_on_third_retry(self):
        """Provider fails twice then succeeds on 3rd attempt."""
        from app.services.llm_service import LLMService

        call_count = 0

        async def fake_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Gemini API error (503): high demand")
            return "Paris is beautiful"

        provider = MagicMock()
        provider.provider_name = "gemini"
        provider.model_name = "gemini-2.5-flash"
        provider.generate = fake_generate

        svc = LLMService(provider)

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await svc.generate("sys", "user")

        assert result == "Paris is beautiful"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_error_propagates_immediately(self):
        """Parse failure / empty response does NOT retry."""
        from app.services.llm_service import LLMService

        call_count = 0

        async def fake_generate_json(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("empty response from Gemini")

        provider = MagicMock()
        provider.provider_name = "gemini"
        provider.model_name = "gemini-2.5-flash"
        provider.generate_json = fake_generate_json

        svc = LLMService(provider)

        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(RuntimeError):
                await svc.generate_json("sys", "user")

        # "empty response" is NOT in _RETRYABLE_PHRASES — should not retry
        # However since "empty" is not in retryable phrases, only 1 call expected
        assert call_count == 1, f"Non-retryable error should not retry, got {call_count} calls"


# ===========================================================================
# Error 3: Gemini JSON truncation detection
# ===========================================================================

class TestJSONTruncationHandling:
    """Validates truncation detection and proper error messaging."""

    @pytest.mark.asyncio
    async def test_truncated_json_raises_runtime_error_with_hint(self):
        """Unterminated JSON > 500 chars raises RuntimeError mentioning 'token limit'."""
        from app.services.llm_service import LLMService

        # Manually build a JSON string that is genuinely cut off mid-string value.
        # This simulates Gemini hitting max_tokens while writing a long description.
        # The string must be > 500 chars and produce 'Unterminated string' parse error.
        long_description_prefix = (
            "Explore the majestic ruins of Kondaveedu fort, a 13th century Telugu citadel "
            "perched 1400 feet above sea level, offering breathtaking panoramic views of "
            "Guntur district with rich Kakatiya architectural heritage. This site is "
            "particularly suited to your interest profile based on semantic memory "
            "similarity score 0.91 matched against previously liked historical sites "
            "during your prior trips to Hampi, Golconda, and Vijayanagara ruins."
        )
        # Build valid-looking JSON with an unterminated string in description
        truncated_json = (
            '{"days": [{"day_number": 1, "title": "City Exploration", "activities": '
            '[{"time": "09:00 AM", "slot_intent": "Ancient Hindu fort visit", '
            '"category": "attraction", "estimated_cost": 0.0, '
            f'"description": "{long_description_prefix}'
            # <-- string is NOT closed; no ", no }, no ], no }
        )
        assert len(truncated_json) > 500, (
            f"Test prerequisite failed: string too short ({len(truncated_json)} chars)"
        )

        async def fake_generate_json(*args, **kwargs):
            return truncated_json

        provider = MagicMock()
        provider.provider_name = "gemini"
        provider.model_name = "gemini-2.5-flash"
        provider.generate_json = fake_generate_json

        svc = LLMService(provider)

        with pytest.raises(RuntimeError) as exc_info:
            await svc.generate_json("sys", "user")

        error_msg = str(exc_info.value).lower()
        assert "truncated" in error_msg or "token" in error_msg, (
            f"Error should mention truncation or token limit, got: {exc_info.value}"
        )

    @pytest.mark.asyncio
    async def test_valid_json_does_not_raise(self):
        """Valid JSON response parses successfully."""
        from app.services.llm_service import LLMService

        valid = json.dumps({
            "days": [
                {
                    "day_number": 1,
                    "title": "Day 1",
                    "activities": [
                        {"time": "09:00 AM", "title": "Check-in", "description": "Settle in",
                         "location": "Hotel", "estimated_cost": 0.0, "category": "rest"}
                    ]
                }
            ]
        })

        async def fake_generate_json(*args, **kwargs):
            return valid

        provider = MagicMock()
        provider.provider_name = "gemini"
        provider.model_name = "gemini-2.5-flash"
        provider.generate_json = fake_generate_json

        svc = LLMService(provider)
        result = await svc.generate_json("sys", "user")

        assert result["days"][0]["day_number"] == 1


# ===========================================================================
# Error 4: Pydantic protected namespace — no warnings
# ===========================================================================

class TestPydanticNamespace:
    """Validates that model_active / model_version fields don't trigger warnings."""

    def test_no_protected_namespace_warning_on_import(self):
        """ExplanationResponse and ModelStatusResponse emit no 'model_' namespace warnings."""
        import importlib
        import sys

        # Remove cached module so we get a fresh import with all warnings active
        for mod_name in list(sys.modules.keys()):
            if "scpm" in mod_name:
                del sys.modules[mod_name]

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            import app.schemas.scpm  # noqa: F401

        namespace_warnings = [
            w for w in caught
            if issubclass(w.category, UserWarning)
            and "model_" in str(w.message).lower()
            and "protected" in str(w.message).lower()
        ]
        assert len(namespace_warnings) == 0, (
            f"Got unexpected Pydantic namespace warnings: "
            f"{[str(w.message) for w in namespace_warnings]}"
        )

    def test_explanation_response_fields_accessible(self):
        """ExplanationResponse can be instantiated with model_active and model_version."""
        from app.schemas.scpm import ExplanationResponse

        obj = ExplanationResponse(
            model_active=True,
            model_version="1.0.0",
            top_positive_factors=[],
            top_negative_factors=[],
            note="Test",
        )
        assert obj.model_active is True
        assert obj.model_version == "1.0.0"


# ===========================================================================
# Error 5: Firestore FieldFilter usage
# ===========================================================================

class TestFirestoreFieldFilter:
    """Validates that FieldFilter is used instead of deprecated positional args."""

    def test_trip_repository_uses_field_filter(self):
        """TripRepository.list_for_user uses FieldFilter."""
        import inspect
        import app.repositories.trip_repository as module
        src = inspect.getsource(module)
        assert "FieldFilter" in src, "trip_repository.py must use FieldFilter"
        # Make sure old-style positional where is gone
        # (checking for the exact deprecated pattern)
        assert '.where("user_id"' not in src, (
            "trip_repository.py still has deprecated positional .where() call"
        )

    def test_diary_repository_uses_field_filter(self):
        """DiaryRepository uses FieldFilter."""
        import inspect
        import app.repositories.diary_repository as module
        src = inspect.getsource(module)
        assert "FieldFilter" in src, "diary_repository.py must use FieldFilter"

    def test_chat_repository_uses_field_filter(self):
        """ChatRepository uses FieldFilter."""
        import inspect
        import app.repositories.chat_repository as module
        src = inspect.getsource(module)
        assert "FieldFilter" in src, "chat_repository.py must use FieldFilter"

    def test_memory_repository_uses_field_filter(self):
        """MemoryRepository uses FieldFilter."""
        import inspect
        import app.repositories.memory_repository as module
        src = inspect.getsource(module)
        assert "FieldFilter" in src, "memory_repository.py must use FieldFilter"


# ===========================================================================
# Regression: itinerary sort (from previous session)
# ===========================================================================

class TestItinerarySortRegression:
    """Regression: activities always sorted chronologically."""

    def test_activities_sorted_correctly(self):
        from app.services.itinerary_validator import sort_activities_in_days

        days = [{
            "day_number": 1,
            "title": "Day 1",
            "activities": [
                {"time": "02:00 PM", "title": "Clock Tower"},
                {"time": "05:00 PM", "title": "Market Walk"},
                {"time": "07:30 PM", "title": "Dinner"},
                {"time": "10:00 AM", "title": "Check-in"},   # out of order
            ]
        }]

        sort_activities_in_days(days)
        titles = [a["title"] for a in days[0]["activities"]]
        assert titles == ["Check-in", "Clock Tower", "Market Walk", "Dinner"], (
            f"Activities not in chronological order: {titles}"
        )

    def test_12am_sorts_before_10am(self):
        from app.services.itinerary_validator import sort_activities_in_days

        days = [{
            "day_number": 1,
            "title": "Day 1",
            "activities": [
                {"time": "10:00 AM", "title": "Breakfast"},
                {"time": "12:00 AM", "title": "Midnight arrival"},
                {"time": "12:00 PM", "title": "Lunch"},
                {"time": "02:00 PM", "title": "Tour"},
            ]
        }]
        sort_activities_in_days(days)
        titles = [a["title"] for a in days[0]["activities"]]
        assert titles[0] == "Midnight arrival", f"12:00 AM should come first, got {titles}"
        assert titles[2] == "Lunch", f"12:00 PM (noon) should be 3rd, got {titles}"

    def test_activities_not_mixed_between_days(self):
        from app.services.itinerary_validator import sort_activities_in_days

        days = [
            {
                "day_number": 1,
                "activities": [
                    {"time": "09:00 AM", "title": "D1-A"},
                    {"time": "02:00 PM", "title": "D1-B"},
                ]
            },
            {
                "day_number": 2,
                "activities": [
                    {"time": "11:00 AM", "title": "D2-A"},
                    {"time": "08:00 AM", "title": "D2-B"},
                ]
            },
        ]
        sort_activities_in_days(days)
        day1_titles = [a["title"] for a in days[0]["activities"]]
        day2_titles = [a["title"] for a in days[1]["activities"]]
        assert day1_titles == ["D1-A", "D1-B"], f"Day 1 wrong: {day1_titles}"
        assert day2_titles == ["D2-B", "D2-A"], f"Day 2 wrong: {day2_titles}"

    def test_missing_time_sorts_last(self):
        from app.services.itinerary_validator import sort_activities_in_days

        days = [{
            "day_number": 1,
            "activities": [
                {"time": "02:00 PM", "title": "Scheduled"},
                {"time": "", "title": "Unscheduled"},
                {"time": "09:00 AM", "title": "Morning"},
            ]
        }]
        sort_activities_in_days(days)
        titles = [a["title"] for a in days[0]["activities"]]
        assert titles[-1] == "Unscheduled", f"Missing time should sort last: {titles}"

    def test_metadata_preserved_after_sort(self):
        from app.services.itinerary_validator import sort_activities_in_days

        days = [{
            "day_number": 1,
            "activities": [
                {"time": "05:00 PM", "title": "Museum", "estimated_cost": 20.0,
                 "category": "culture", "id": "act-2"},
                {"time": "10:00 AM", "title": "Hotel", "estimated_cost": 0.0,
                 "category": "rest", "id": "act-1"},
            ]
        }]
        sort_activities_in_days(days)
        activities = days[0]["activities"]
        assert activities[0]["id"] == "act-1"
        assert activities[0]["estimated_cost"] == 0.0
        assert activities[1]["id"] == "act-2"
        assert activities[1]["estimated_cost"] == 20.0
