# LLM Provider package for SmartTrip AI.
# All text generation (itinerary, chat, diary, Q&A) uses GeminiTextProvider.
# Groq and OpenAI providers are retained in the file system but are NOT active.
from app.services.providers.base import BaseLLMProvider
from app.services.providers.gemini_provider import GeminiTextProvider

__all__ = ["BaseLLMProvider", "GeminiTextProvider"]
