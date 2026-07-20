"""
Gemini AI wrapper using the Google Gen AI SDK (google-genai).

Every failure mode in this module is normalized to `RuntimeError` on
purpose: both `routes/chat.py` and `routes/trips.py` already catch
`RuntimeError` and translate it into a clean `503` with a useful message.
Letting any other exception type escape this module (an SDK-specific
`errors.APIError`, a bare `json.JSONDecodeError`, an `AttributeError` from
touching `.text` on an empty response) bypasses that handling entirely and
surfaces as an opaque, undiagnosable 500 to the client.
"""
from __future__ import annotations

import json

from google import genai
from google.genai import errors, types

from app.core.config import get_settings

settings = get_settings()

# Client construction itself doesn't make a network call, so it's safe to
# do at import time — but we deliberately do NOT validate the API key here.
# Doing so would crash the whole app at startup (breaking /health and every
# other route) just because Gemini isn't configured yet. Validation happens
# per-call in `_ensure_configured` instead, scoped to only the AI endpoints.
client = genai.Client(api_key=settings.GEMINI_API_KEY or "")


def _ensure_configured() -> None:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")


def _extract_text(response: types.GenerateContentResponse) -> str:
    """
    `.text` raises if the response has no valid text part — e.g. the prompt
    was safety-blocked, or the model returned only a function call. Surface
    that as a clear RuntimeError instead of letting the SDK's own exception
    (or an AttributeError, depending on SDK version) propagate raw.
    """
    try:
        text = response.text
    except Exception as exc:  # SDK exception type varies by version/cause
        raise RuntimeError("Gemini returned no usable text in its response") from exc

    if not text:
        finish_reason = getattr(response.candidates[0], "finish_reason", None) if response.candidates else None
        raise RuntimeError(f"Gemini returned an empty response (finish_reason={finish_reason})")

    return text


async def generate_json(*, system_prompt: str, user_prompt: str) -> dict:
    """Call Gemini and parse a strict-JSON object out of the response text."""
    _ensure_configured()

    prompt = f"{system_prompt}\n\nUser:\n{user_prompt}"

    try:
        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
    except errors.APIError as exc:
        # e.code / e.message come from the Gemini API itself (auth failure,
        # invalid model name, quota exceeded, etc.) — pass them through so
        # the 503 the client sees actually explains what went wrong.
        raise RuntimeError(f"Gemini API error ({exc.code}): {exc.message}") from exc

    text = _extract_text(response)

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini did not return valid JSON") from exc


async def generate_text(*, system_prompt: str, history: list[dict], user_prompt: str) -> str:
    """Multi-turn chat completion."""
    _ensure_configured()

    conversation = system_prompt + "\n\n"
    for message in history:
        role = "User" if message["role"] == "user" else "Assistant"
        conversation += f"{role}: {message['content']}\n"
    conversation += f"User: {user_prompt}"

    try:
        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=conversation,
        )
    except errors.APIError as exc:
        raise RuntimeError(f"Gemini API error ({exc.code}): {exc.message}") from exc

    return _extract_text(response)
