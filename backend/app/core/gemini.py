"""
Gemini AI wrapper using the new Google Gen AI SDK.
"""

from __future__ import annotations

import json

from google import genai
from google.genai import types

from app.core.config import get_settings

settings = get_settings()

client = genai.Client(
    api_key=settings.GEMINI_API_KEY,
)


async def generate_json(
    *,
    system_prompt: str,
    user_prompt: str,
) -> dict:
    """
    Generate a JSON response from Gemini.
    """

    prompt = f"""
{system_prompt}

User:
{user_prompt}
"""

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    return json.loads(response.text)


async def generate_text(
    *,
    system_prompt: str,
    history: list[dict],
    user_prompt: str,
) -> str:
    """
    Multi-turn chat completion.
    """

    conversation = system_prompt + "\n\n"

    for message in history:
        role = "User" if message["role"] == "user" else "Assistant"
        conversation += f"{role}: {message['content']}\n"

    conversation += f"User: {user_prompt}"

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=conversation,
    )

    return response.text
