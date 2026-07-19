from __future__ import annotations

import json
import google.generativeai as genai

import app.core.config as config_module
from app.core.config import get_settings

print("=" * 80)
print("CONFIG MODULE:", config_module.__file__)
print("SETTINGS CLASS:", config_module.Settings)
print("FIELDS:", list(config_module.Settings.model_fields.keys()))
print("=" * 80)

settings = get_settings()
_configured = False


def _ensure_configured():
    global _configured

    print("Settings object:", settings)
    print("Has GEMINI_API_KEY:", hasattr(settings, "GEMINI_API_KEY"))

    if not _configured:
        if not hasattr(settings, "GEMINI_API_KEY"):
            raise RuntimeError(
                f"GEMINI_API_KEY missing. Fields={list(config_module.Settings.model_fields.keys())}"
            )

        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set")

        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True


async def generate_json(*, system_prompt: str, user_prompt: str):
    _ensure_configured()
    model = genai.GenerativeModel(settings.GEMINI_MODEL, system_instruction=system_prompt)
    response = await model.generate_content_async(
        user_prompt,
        generation_config={"response_mime_type": "application/json"},
    )
    return json.loads(response.text)


async def generate_text(*, system_prompt: str, history: list[dict], user_prompt: str):
    _ensure_configured()
    model = genai.GenerativeModel(settings.GEMINI_MODEL, system_instruction=system_prompt)
    chat = model.start_chat(
        history=[
            {
                "role": "user" if m["role"] == "user" else "model",
                "parts": [m["content"]],
            }
            for m in history
        ]
    )
    response = await chat.send_message_async(user_prompt)
    return response.text
