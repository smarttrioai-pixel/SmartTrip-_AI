"""
Weather Service Integration for SmartTrip AI.
Fetches real-time weather forecasts using Open-Meteo or OpenWeatherMap API,
with graceful fallback and local caching.
"""
from __future__ import annotations

import logging
from typing import Any
import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

class WeatherService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._cache: dict[str, dict[str, Any]] = {}

    async def get_forecast(self, lat: float, lon: float, date_str: str | None = None) -> dict[str, Any]:
        cache_key = f"{round(lat, 2)},{round(lon, 2)}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            # Use Open-Meteo free public API as zero-key fallback or primary
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    current = data.get("current_weather", {})
                    temp = current.get("temperature", 22.0)
                    weather_code = current.get("weathercode", 0)
                    
                    # Map WMO weather codes to condition
                    condition = "Clear"
                    if weather_code in [1, 2, 3]:
                        condition = "Partly Cloudy"
                    elif weather_code in [45, 48]:
                        condition = "Foggy"
                    elif weather_code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
                        condition = "Rainy"
                    elif weather_code in [71, 73, 75, 77, 85, 86]:
                        condition = "Snowy"
                    elif weather_code >= 95:
                        condition = "Thunderstorm"

                    result = {
                        "temperature": temp,
                        "condition": condition,
                        "weather_code": weather_code,
                        "wind_speed": current.get("windspeed", 10.0),
                        "is_suitable_outdoor": condition not in ["Rainy", "Snowy", "Thunderstorm"],
                        "suitability_score": 0.4 if condition in ["Rainy", "Thunderstorm"] else 0.9,
                    }
                    self._cache[cache_key] = result
                    return result
        except Exception as e:
            logger.warning("Weather API call failed, using fallback forecast: %s", e)

        fallback = {
            "temperature": 22.0,
            "condition": "Clear",
            "weather_code": 0,
            "wind_speed": 8.0,
            "is_suitable_outdoor": True,
            "suitability_score": 0.85,
        }
        return fallback

_weather_service = WeatherService()

def get_weather_service() -> WeatherService:
    return _weather_service
