"""
Thin wrapper around google-generativeai so the rest of the app depends on
this module's interface, not the SDK directly (easier to mock in tests, and
easier to swap models/providers later).
"""
from __future__ import annotations

import json

import google.generativeai as genai

from app.core.config import get_settings
import app.core.config as config_module

print("CONFIG FILE:", config_module.__file__)
print("SETTINGS FIELDS:", list(config_module.Settings.model_fields.keys()))

settings = get_settings()
_configured = False


def _ensure_configured() -> None:
    global _configured
    if not _configured:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True


async def generate_json(*, system_prompt: str, user_prompt: str) -> dict:
    """Call Gemini and parse a JSON object out of the response text."""
    _ensure_configured()
    model = genai.GenerativeModel(settings.GEMINI_MODEL, system_instruction=system_prompt)
    response = await model.generate_content_async(
        user_prompt,
        generation_config={"response_mime_type": "application/json"},
    )
    return json.loads(response.text)


async def generate_text(*, system_prompt: str, history: list[dict], user_prompt: str) -> str:
    """Multi-turn chat completion. `history` is a list of {role, content}."""
    _ensure_configured()
    model = genai.GenerativeModel(settings.GEMINI_MODEL, system_instruction=system_prompt)
    chat = model.start_chat(
        history=[
            {"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]}
            for m in history
        ]
    )
    response = await chat.send_message_async(user_prompt)
    return response.text
