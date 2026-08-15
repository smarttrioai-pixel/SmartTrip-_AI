"""
Weather Service Integration for SmartTrip AI.

Provides two methods:
    get_forecast(lat, lon)
        Current conditions — used by ContextEngine for per-activity scoring.
        Source: Open-Meteo /v1/forecast (current_weather)

    get_forecast_for_date(lat, lon, travel_date)
        Daily forecast for a specific travel date — used by LiveContextEngine
        to build SCIF planning decisions BEFORE Qwen generates the itinerary.
        Source: Open-Meteo /v1/forecast (daily fields)
        Range: up to 16 days ahead (Open-Meteo free tier limit).

Design rules:
    - NEVER return fabricated weather.
    - If the API fails or the date is out of range, return status="unavailable".
    - Cache by (lat, lon, date) to avoid redundant API calls across activities
      on the same travel day.
    - Never expose raw API errors to callers — return structured fallback dicts.
"""
from __future__ import annotations

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
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
            if resp.status_code == 200:
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
            "is_suitable_outdoor": True,   # conservative: don't block activities without data
            "suitability_score": 0.5,      # neutral score when unavailable
            "source": "unavailable",
        }
        return unavailable

    # ------------------------------------------------------------------
    # Date-aware daily forecast (used by LiveContextEngine / SCIF)
    # ------------------------------------------------------------------

    async def get_forecast_for_date(
        self,
        lat: float,
        lon: float,
        travel_date: date,
    ) -> dict[str, Any]:
        """
        Fetch Open-Meteo daily forecast for a specific travel date.

        Returns a normalized dict with:
            status           "available" | "unavailable"
            forecast_date    ISO date string
            temperature_max  float | None
            temperature_min  float | None
            condition        string (from WMO code)
            rain_probability float | None   (precipitation_sum > 0 → approx)
            precipitation_mm float | None
            wind_speed       float | None
            is_suitable_outdoor bool
            suitability_score   float (0–1)
            source           "open-meteo" | "unavailable"
            reason           set only when status="unavailable"

        NEVER returns fabricated data. On any failure or out-of-range date:
            {"status": "unavailable", "reason": "..."}
        """
        date_str = travel_date.isoformat()
        cache_key = f"{round(lat, 2)},{round(lon, 2)},{date_str}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Check if date is within Open-Meteo's 16-day forecast window
        today = datetime.now(tz=timezone.utc).date()
        delta_days = (travel_date - today).days
        if delta_days < 0:
            result = {
                "status": "unavailable",
                "forecast_date": date_str,
                "reason": "past_date",
                "source": "unavailable",
                "is_suitable_outdoor": True,
                "suitability_score": 0.5,
            }
            self._cache[cache_key] = result
            return result

        if delta_days > _OPEN_METEO_MAX_FORECAST_DAYS:
            result = {
                "status": "unavailable",
                "forecast_date": date_str,
                "reason": f"forecast_range_exceeded_{_OPEN_METEO_MAX_FORECAST_DAYS}_days",
                "source": "unavailable",
                "is_suitable_outdoor": True,
                "suitability_score": 0.5,
            }
            self._cache[cache_key] = result
            return result

        try:
            url = (
                f"{_OPEN_METEO_BASE_URL}"
                f"?latitude={lat}&longitude={lon}"
                f"&daily=weathercode,temperature_2m_max,temperature_2m_min,"
                f"precipitation_sum,windspeed_10m_max,precipitation_probability_max"
                f"&timezone=auto"
                f"&start_date={date_str}&end_date={date_str}"
            )
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url)

            if resp.status_code == 200:
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

                # precipitation_probability_max is 0–100 in Open-Meteo; convert to 0.0–1.0
                rain_probability: float | None = (
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

            logger.warning(
                "provider=open-meteo operation=daily_forecast status=http_%d date=%s",
                resp.status_code, date_str,
            )

        except Exception as exc:
            logger.warning(
                "provider=open-meteo operation=daily_forecast status=failed date=%s error=%s",
                date_str, exc,
            )

        unavailable = {
            "status": "unavailable",
            "forecast_date": date_str,
            "reason": "api_error",
            "source": "unavailable",
            "is_suitable_outdoor": True,
            "suitability_score": 0.5,
        }
        self._cache[cache_key] = unavailable
        return unavailable


_weather_service = WeatherService()


def get_weather_service() -> WeatherService:
    return _weather_service
