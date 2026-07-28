"""
Gemini Vision Integration for SmartTrip AI.

Performs actual multimodal landmark identification — the image is sent to
Gemini, not just a text hint describing it. Previously, image_bytes/
image_b64 parameters were accepted but never used; only prompt_hint text
was sent to Gemini (text-only, via generate_json). On ANY failure —
including simply not being configured — it fell back to a hardcoded
"Eiffel Tower" response with fake confidence 0.98 and a stock photo URL,
meaning it would confidently misidentify literally any landmark, anywhere,
as the Eiffel Tower whenever the real call failed. That fallback is gone;
failures now raise, matching every other AI call's error handling in this
codebase, and a low-confidence/unidentified result is reported honestly
rather than guessed.
"""
from __future__ import annotations

import base64
import logging
from typing import Any

from app.core.gemini import generate_json_from_image
from app.integrations.wikipedia_service import get_wikipedia_service

logger = logging.getLogger(__name__)

VISION_PROMPT = """Analyze this image of a travel landmark or location.
Return ONLY a valid JSON object matching this schema:
{
  "landmark_name": "Name of landmark or location, or null if not identifiable",
  "confidence": 0.0,
  "category": "Architecture | Nature | Historic | Cultural | Unknown",
  "historical_background": "Short 2-3 sentence overview of historical significance, if known.",
  "architectural_highlights": ["Key architectural feature 1", "Key feature 2"],
  "cultural_importance": "Cultural context or local tradition, if known.",
  "photography_spots": ["Best angle from east side", "Sunset view point"],
  "nearby_attractions": ["Nearby museum", "Local plaza"]
}
If the image does not clearly show an identifiable landmark, set landmark_name
to null and confidence to a low value (below 0.3) rather than guessing."""


class GeminiVisionService:
    def __init__(self) -> None:
        self.wiki = get_wikipedia_service()

    async def analyze_landmark_image(
        self, image_bytes: bytes | None = None, image_b64: str | None = None, prompt_hint: str = ""
    ) -> dict[str, Any]:
        """
        Analyzes an actual landmark photo via Gemini Vision. Raises
        RuntimeError (not a fabricated fallback) if no image is provided or
        analysis fails — callers surface this as a real error, never
        substitute a guess.
        """
        if image_bytes is None and image_b64:
            image_bytes = base64.b64decode(image_b64)
        if not image_bytes:
            raise RuntimeError("No image provided for landmark analysis")

        user_prompt = f"User note/hint: '{prompt_hint or 'none provided'}'"
        ai_data = await generate_json_from_image(
            system_prompt=VISION_PROMPT, user_prompt=user_prompt, image_bytes=image_bytes
        )

        landmark_name = ai_data.get("landmark_name")
        confidence = ai_data.get("confidence", 0.0)

        result: dict[str, Any] = {
            "landmark_name": landmark_name,
            "confidence": confidence,
            "category": ai_data.get("category", "Unknown"),
            "historical_background": ai_data.get("historical_background", ""),
            "architectural_highlights": ai_data.get("architectural_highlights", []),
            "cultural_importance": ai_data.get("cultural_importance", ""),
            "photography_spots": ai_data.get("photography_spots", []),
            "nearby_attractions": ai_data.get("nearby_attractions", []),
            "thumbnail_url": "",
            "wikipedia_url": "",
        }

        # Enrich with real Wikipedia data only when Gemini is actually
        # confident it identified something real — a low-confidence guess
        # shouldn't get "confirmed" by a Wikipedia lookup for the wrong name.
        if landmark_name and confidence >= 0.5:
            try:
                wiki_data = await self.wiki.get_landmark_info(landmark_name)
                if wiki_data:
                    result["thumbnail_url"] = wiki_data.get("thumbnail_url", "")
                    result["wikipedia_url"] = wiki_data.get("wikipedia_url", "")
                    if not result["historical_background"]:
                        result["historical_background"] = wiki_data.get("summary", "")
            except Exception as e:
                logger.warning("Wikipedia enrichment failed for '%s': %s", landmark_name, e)

        return result


_gemini_vision_service = GeminiVisionService()


def get_gemini_vision_service() -> GeminiVisionService:
    return _gemini_vision_service
