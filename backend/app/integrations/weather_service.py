"""
Weather Service Integration for SmartTrip AI.

Provides two methods:
    get_forecast(lat, lon)
        Current conditions — used by ContextEngine for per-activity scoring.
        Source: Open-Meteo /v1/forecast (current_weather)

    get_forecast_for_date(lat, lon, travel_date)
        Daily forecast for a specific travel date — used by LiveContextEngine
        to build SCIF planning decisions BEFORE Gemini generates the itinerary.
        Source: Open-Meteo /v1/forecast (daily fields)
        Range: up to 16 days ahead (Open-Meteo free tier limit).

    get_forecast_range(lat, lon, start_date, end_date)
        Batches ALL travel dates into a SINGLE Open-Meteo HTTP request.
        This is the PREFERRED method for itinerary generation — it replaces
        the per-day loop in LiveContextEngine which caused HTTP 429 errors.

Design rules:
    - NEVER return fabricated weather.
    - If the API fails or the date is out of range, return status="unavailable".
    - Cache by (lat, lon, date) to avoid redundant API calls across activities
      on the same travel day.
    - Never expose raw API errors to callers — return structured fallback dicts.
    - Retry 429 responses with exponential backoff (max 3 attempts).
    - Respect Retry-After header when present.
    - Timeout: 10 seconds per request.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone, timedelta
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Open-Meteo WMO weather code → human-readable condition
_WMO_CONDITION_MAP: dict[int, str] = {
    0: "Clear",
    1: "Mostly Clear", 2: "Partly Cloudy", 3: "Overcast",
    45: "Foggy", 48: "Foggy",
    51: "Light Drizzle", 53: "Drizzle", 55: "Heavy Drizzle",
    61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
    71: "Light Snow", 73: "Snow", 75: "Heavy Snow", 77: "Snow Grains",
    80: "Showers", 81: "Heavy Showers", 82: "Violent Showers",
    85: "Snow Showers", 86: "Heavy Snow Showers",
    95: "Thunderstorm", 96: "Thunderstorm with Hail", 99: "Thunderstorm with Heavy Hail",
}

_OUTDOOR_UNSUITABLE = {"Rain", "Heavy Rain", "Showers", "Heavy Showers", "Violent Showers",
                        "Thunderstorm", "Thunderstorm with Hail", "Thunderstorm with Heavy Hail",
                        "Snow", "Heavy Snow", "Drizzle", "Heavy Drizzle"}

# Open-Meteo free tier: daily forecasts available up to 16 days ahead
_OPEN_METEO_MAX_FORECAST_DAYS = 16
_OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"
_REQUEST_TIMEOUT = 10.0   # seconds
_MAX_RETRIES = 3
_RETRY_BASE_BACKOFF = 1.0  # seconds — doubles each attempt


def _condition_from_code(code: int) -> str:
    return _WMO_CONDITION_MAP.get(code, "Unknown")


def _suitability(condition: str) -> float:
    if condition in _OUTDOOR_UNSUITABLE:
        return 0.4
    if condition in {"Overcast", "Foggy", "Light Drizzle", "Light Rain"}:
        return 0.65
    return 0.90


def _is_suitable_outdoor(condition: str) -> bool:
    return condition not in _OUTDOOR_UNSUITABLE


def _unavailable_day(date_str: str, reason: str = "api_error") -> dict[str, Any]:
    """Structured unavailable weather result — consistent shape."""
    return {
        "status": "unavailable",
        "forecast_date": date_str,
        "reason": reason,
        "source": "unavailable",
        "is_suitable_outdoor": True,   # conservative: don't block without data
        "suitability_score": 0.5,      # neutral
    }


async def _http_get_with_retry(url: str) -> httpx.Response | None:
    """
    Execute an HTTP GET with exponential backoff on 429 / 503 errors.
    Returns the response on success (200), None on unrecoverable failure.
    Respects Retry-After header when present.
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                resp = await client.get(url)

            if resp.status_code == 200:
                return resp

            if resp.status_code == 429:
                # Respect Retry-After if present, otherwise exponential backoff
                retry_after_raw = resp.headers.get("Retry-After")
                if retry_after_raw:
                    try:
                        wait = float(retry_after_raw)
                    except ValueError:
                        wait = _RETRY_BASE_BACKOFF * (2 ** (attempt - 1))
                else:
                    wait = _RETRY_BASE_BACKOFF * (2 ** (attempt - 1))

                wait = min(wait, 30.0)  # cap at 30 s
                logger.warning(
                    "provider=open-meteo status=http_429 attempt=%d/%d "
                    "retry_after=%.1fs",
                    attempt, _MAX_RETRIES, wait,
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(wait)
                    continue
                return None  # exhausted retries

            if resp.status_code in (500, 502, 503, 504):
                wait = _RETRY_BASE_BACKOFF * (2 ** (attempt - 1))
                logger.warning(
                    "provider=open-meteo status=http_%d attempt=%d/%d "
                    "retry_in=%.1fs",
                    resp.status_code, attempt, _MAX_RETRIES, wait,
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(wait)
                    continue
                return None

            # Other non-200 status — log and return None
            logger.warning(
                "provider=open-meteo status=http_%d (non-retryable)",
                resp.status_code,
            )
            return None

        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            wait = _RETRY_BASE_BACKOFF * (2 ** (attempt - 1))
            logger.warning(
                "provider=open-meteo connection_error=%s attempt=%d/%d "
                "retry_in=%.1fs",
                exc, attempt, _MAX_RETRIES, wait,
            )
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(wait)
            else:
                return None

        except Exception as exc:
            logger.warning("provider=open-meteo unexpected_error=%s", exc)
            return None

    return None


class WeatherService:
    def __init__(self) -> None:
        self.settings = get_settings()
        # Cache keyed by "lat,lon" for current, "lat,lon,YYYY-MM-DD" for daily
        self._cache: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Current conditions (used by ContextEngine / RecommendationEngine)
    # ------------------------------------------------------------------

    async def get_forecast(self, lat: float, lon: float, date_str: str | None = None) -> dict[str, Any]:
        """
        Fetch current weather conditions for lat/lon.
        Returns a normalized dict with suitability_score.
        On failure: returns a fallback with status='unavailable'.
        NEVER fabricates weather data.
        """
        cache_key = f"{round(lat, 2)},{round(lon, 2)}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            url = (
                f"{_OPEN_METEO_BASE_URL}"
                f"?latitude={lat}&longitude={lon}"
                f"&current_weather=true"
                f"&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum"
                f"&timezone=auto"
            )
            resp = await _http_get_with_retry(url)
            if resp is not None and resp.status_code == 200:
                data = resp.json()
                current = data.get("current_weather", {})
                code = current.get("weathercode", 0)
                condition = _condition_from_code(code)
                result = {
                    "status": "available",
                    "temperature": current.get("temperature", 22.0),
                    "condition": condition,
                    "weather_code": code,
                    "wind_speed": current.get("windspeed", 10.0),
                    "is_suitable_outdoor": _is_suitable_outdoor(condition),
                    "suitability_score": _suitability(condition),
                    "source": "open-meteo",
                }
                self._cache[cache_key] = result
                return result
        except Exception as exc:
            logger.warning("provider=open-meteo operation=current_forecast status=failed error=%s", exc)

        unavailable = {
            "status": "unavailable",
            "temperature": None,
            "condition": None,
            "weather_code": None,
            "wind_speed": None,
            "is_suitable_outdoor": True,
            "suitability_score": 0.5,
            "source": "unavailable",
        }
        return unavailable

    # ------------------------------------------------------------------
    # BATCH range forecast — SINGLE HTTP request for all travel dates
    # This is the preferred method for itinerary generation.
    # Replaces the per-day loop that was causing HTTP 429 errors.
    # ------------------------------------------------------------------

    async def get_forecast_range(
        self,
        lat: float,
        lon: float,
        start_date: date,
        end_date: date,
    ) -> dict[date, dict[str, Any]]:
        """
        Fetch Open-Meteo daily forecasts for ALL dates in [start_date, end_date]
        in a SINGLE HTTP request.

        Returns a dict mapping each date → weather result dict.
        Dates outside the 16-day forecast window get status="unavailable".
        On API failure, all dates get status="unavailable" — caller must continue.

        This replaces calling get_forecast_for_date() in a per-day loop.
        """
        today = datetime.now(tz=timezone.utc).date()

        # Collect all dates in range
        all_dates: list[date] = []
        cur = start_date
        while cur <= end_date:
            all_dates.append(cur)
            cur += timedelta(days=1)

        result: dict[date, dict[str, Any]] = {}

        # Separate past / out-of-range / in-range dates
        in_range_dates = []
        for d in all_dates:
            delta = (d - today).days
            if delta < 0:
                result[d] = _unavailable_day(d.isoformat(), "past_date")
            elif delta > _OPEN_METEO_MAX_FORECAST_DAYS:
                result[d] = _unavailable_day(
                    d.isoformat(),
                    f"forecast_range_exceeded_{_OPEN_METEO_MAX_FORECAST_DAYS}_days",
                )
            else:
                # Check per-date cache first
                cache_key = f"{round(lat, 2)},{round(lon, 2)},{d.isoformat()}"
                if cache_key in self._cache:
                    result[d] = self._cache[cache_key]
                else:
                    in_range_dates.append(d)

        if not in_range_dates:
            return result

        # Build a single request for all in-range dates
        batch_start = min(in_range_dates).isoformat()
        batch_end = max(in_range_dates).isoformat()

        url = (
            f"{_OPEN_METEO_BASE_URL}"
            f"?latitude={lat}&longitude={lon}"
            f"&daily=weathercode,temperature_2m_max,temperature_2m_min,"
            f"precipitation_sum,windspeed_10m_max,precipitation_probability_max"
            f"&timezone=auto"
            f"&start_date={batch_start}&end_date={batch_end}"
        )

        try:
            resp = await _http_get_with_retry(url)
            if resp is None:
                logger.warning(
                    "provider=open-meteo operation=range_forecast status=failed "
                    "batch=%s_to_%s — weather unavailable, continuing without it",
                    batch_start, batch_end,
                )
                for d in in_range_dates:
                    result[d] = _unavailable_day(d.isoformat(), "api_error")
                return result

            data = resp.json()
            daily = data.get("daily", {})
            dates_returned = daily.get("time", [])
            codes = daily.get("weathercode", [])
            t_max_list = daily.get("temperature_2m_max", [])
            t_min_list = daily.get("temperature_2m_min", [])
            precip_list = daily.get("precipitation_sum", [])
            wind_list = daily.get("windspeed_10m_max", [])
            precip_prob_list = daily.get("precipitation_probability_max", [])

            for i, date_str in enumerate(dates_returned):
                try:
                    d = date.fromisoformat(date_str)
                except ValueError:
                    continue

                if i >= len(codes):
                    result[d] = _unavailable_day(date_str, "missing_data")
                    continue

                code = codes[i]
                condition = _condition_from_code(code)
                t_max = t_max_list[i] if i < len(t_max_list) else None
                t_min = t_min_list[i] if i < len(t_min_list) else None
                precip_mm = precip_list[i] if i < len(precip_list) else None
                wind_speed = wind_list[i] if i < len(wind_list) else None
                precip_prob_raw = precip_prob_list[i] if i < len(precip_prob_list) else None
                rain_probability = (
                    round(precip_prob_raw / 100.0, 2) if precip_prob_raw is not None else None
                )

                day_result: dict[str, Any] = {
                    "status": "available",
                    "forecast_date": date_str,
                    "temperature_max": t_max,
                    "temperature_min": t_min,
                    "condition": condition,
                    "weather_code": code,
                    "precipitation_mm": precip_mm,
                    "rain_probability": rain_probability,
                    "wind_speed": wind_speed,
                    "is_suitable_outdoor": _is_suitable_outdoor(condition),
                    "suitability_score": _suitability(condition),
                    "source": "open-meteo",
                }
                logger.info(
                    "provider=open-meteo operation=range_forecast "
                    "date=%s condition=%s rain_prob=%s suitability=%.2f",
                    date_str, condition, rain_probability, _suitability(condition),
                )
                cache_key = f"{round(lat, 2)},{round(lon, 2)},{date_str}"
                self._cache[cache_key] = day_result
                result[d] = day_result

            # Any in_range_dates not covered by the response → unavailable
            for d in in_range_dates:
                if d not in result:
                    result[d] = _unavailable_day(d.isoformat(), "not_in_response")

        except Exception as exc:
            logger.warning(
                "provider=open-meteo operation=range_forecast status=exception "
                "error=%s — weather unavailable, continuing without it",
                exc,
            )
            for d in in_range_dates:
                if d not in result:
                    result[d] = _unavailable_day(d.isoformat(), "exception")

        return result

    # ------------------------------------------------------------------
    # Date-aware daily forecast (single date — kept for backward compat)
    # ------------------------------------------------------------------

    async def get_forecast_for_date(
        self,
        lat: float,
        lon: float,
        travel_date: date,
    ) -> dict[str, Any]:
        """
        Fetch Open-Meteo daily forecast for a specific travel date.
        Uses the cache when available.
        For itinerary generation, prefer get_forecast_range() to batch all dates.
        """
        date_str = travel_date.isoformat()
        cache_key = f"{round(lat, 2)},{round(lon, 2)},{date_str}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Check if date is within Open-Meteo's 16-day forecast window
        today = datetime.now(tz=timezone.utc).date()
        delta_days = (travel_date - today).days
        if delta_days < 0:
            result = _unavailable_day(date_str, "past_date")
            self._cache[cache_key] = result
            return result

        if delta_days > _OPEN_METEO_MAX_FORECAST_DAYS:
            result = _unavailable_day(
                date_str,
                f"forecast_range_exceeded_{_OPEN_METEO_MAX_FORECAST_DAYS}_days",
            )
            self._cache[cache_key] = result
            return result

        url = (
            f"{_OPEN_METEO_BASE_URL}"
            f"?latitude={lat}&longitude={lon}"
            f"&daily=weathercode,temperature_2m_max,temperature_2m_min,"
            f"precipitation_sum,windspeed_10m_max,precipitation_probability_max"
            f"&timezone=auto"
            f"&start_date={date_str}&end_date={date_str}"
        )

        try:
            resp = await _http_get_with_retry(url)
            if resp is not None and resp.status_code == 200:
                data = resp.json()
                daily = data.get("daily", {})
                codes = daily.get("weathercode", [])
                if not codes:
                    raise ValueError("Empty weathercode in Open-Meteo response")

                code = codes[0]
                condition = _condition_from_code(code)
                t_max_list = daily.get("temperature_2m_max", [None])
                t_min_list = daily.get("temperature_2m_min", [None])
                precip_list = daily.get("precipitation_sum", [None])
                wind_list = daily.get("windspeed_10m_max", [None])
                precip_prob_list = daily.get("precipitation_probability_max", [None])

                t_max = t_max_list[0] if t_max_list else None
                t_min = t_min_list[0] if t_min_list else None
                precip_mm = precip_list[0] if precip_list else None
                wind_speed = wind_list[0] if wind_list else None
                precip_prob_raw = precip_prob_list[0] if precip_prob_list else None
                rain_probability = (
                    round(precip_prob_raw / 100.0, 2) if precip_prob_raw is not None else None
                )

                result = {
                    "status": "available",
                    "forecast_date": date_str,
                    "temperature_max": t_max,
                    "temperature_min": t_min,
                    "condition": condition,
                    "weather_code": code,
                    "precipitation_mm": precip_mm,
                    "rain_probability": rain_probability,
                    "wind_speed": wind_speed,
                    "is_suitable_outdoor": _is_suitable_outdoor(condition),
                    "suitability_score": _suitability(condition),
                    "source": "open-meteo",
                }
                logger.info(
                    "provider=open-meteo operation=daily_forecast "
                    "date=%s condition=%s rain_prob=%s suitability=%.2f lat=%.2f lon=%.2f",
                    date_str, condition, rain_probability,
                    _suitability(condition), lat, lon,
                )
                self._cache[cache_key] = result
                return result

        except Exception as exc:
            logger.warning(
                "provider=open-meteo operation=daily_forecast status=failed date=%s error=%s",
                date_str, exc,
            )

        unavailable = _unavailable_day(date_str, "api_error")
        self._cache[cache_key] = unavailable
        return unavailable


_weather_service = WeatherService()


def get_weather_service() -> WeatherService:
    return _weather_service
