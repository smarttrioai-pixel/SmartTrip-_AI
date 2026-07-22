"""
Wikipedia & Wikimedia Service Integration for SmartTrip AI.
Fetches detailed historical summaries, architectural descriptions, photo URLs,
and cultural highlights for landmarks and destinations.
"""
from __future__ import annotations

import logging
from typing import Any
import httpx

logger = logging.getLogger(__name__)

class WikipediaService:
    def __init__(self) -> None:
        self._summary_cache: dict[str, dict[str, Any]] = {}

    async def get_landmark_info(self, landmark_name: str) -> dict[str, Any]:
        """Fetch summary, extract, image thumbnail, and page URL from Wikipedia REST API."""
        if landmark_name in self._summary_cache:
            return self._summary_cache[landmark_name]

        try:
            formatted_title = landmark_name.strip().replace(" ", "_")
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{formatted_title}"
            headers = {"User-Agent": "SmartTripAI/2.0 (contact@smarttrip.ai)"}

            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    extract = data.get("extract", "")
                    thumbnail = data.get("thumbnail", {}).get("source", "")
                    page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")

                    result = {
                        "title": data.get("title", landmark_name),
                        "summary": extract or f"Historical landmark and destination: {landmark_name}.",
                        "thumbnail_url": thumbnail,
                        "wikipedia_url": page_url,
                        "description": data.get("description", "Tourist Attraction"),
                    }
                    self._summary_cache[landmark_name] = result
                    return result
        except Exception as e:
            logger.warning("Wikipedia API lookup failed for '%s': %s", landmark_name, e)

        fallback = {
            "title": landmark_name,
            "summary": f"{landmark_name} is a renowned destination known for its cultural heritage, architectural significance, and vibrant atmosphere.",
            "thumbnail_url": "https://images.unsplash.com/photo-1503220317375-aaad61436b1b?w=600&auto=format&fit=crop",
            "wikipedia_url": f"https://en.wikipedia.org/wiki/{landmark_name.replace(' ', '_')}",
            "description": "Cultural Landmark",
        }
        return fallback

_wikipedia_service = WikipediaService()

def get_wikipedia_service() -> WikipediaService:
    return _wikipedia_service
