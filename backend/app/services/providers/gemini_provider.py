"""
Gemini Text Provider for SmartTrip AI — Multi-Key Rotation.

This provider wraps the Google Gemini generative API for ALL text generation tasks:
  - Itinerary generation (planning_engine.py)
  - AI Tour Guide / Chat (chat_service.py)
  - Travel Diary story generation (diary_service.py)
  - Landmark Q&A (explore.py)
  - Alternatives recommendation (alternatives_service.py)

MULTI-KEY ROTATION:
  - Accepts a list of API keys via GEMINI_API_KEYS env var (comma-separated).
  - On 429 ResourceExhausted / quota errors, automatically rotates to the next key.
  - Cycles through ALL keys before raising a final RuntimeError.
  - Each key gets its own genai.Client instance for clean isolation.

VISION is NOT part of this provider.
Vision stays in app/integrations/gemini_vision_service.py and
app/core/gemini.py — completely separate from the LLM provider layer.

All SDK errors are normalized to RuntimeError before returning.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from google import genai
from google.genai import errors, types

from app.services.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)

# HTTP status codes / error codes that indicate quota exhaustion → rotate key
_QUOTA_CODES = {429, 503, 8}  # 8 = gRPC RESOURCE_EXHAUSTED


def _is_quota_error(exc: Exception) -> bool:
    """Return True if the exception is a rate-limit / quota error."""
    if isinstance(exc, errors.APIError):
        code = getattr(exc, "code", None)
        if code in _QUOTA_CODES:
            return True
        msg = str(exc).lower()
        if any(kw in msg for kw in ("quota", "rate limit", "resource_exhausted", "429")):
            return True
    # Catch plain RuntimeError wrapping quota messages (should not happen, but safety net)
    msg = str(exc).lower()
    return any(kw in msg for kw in ("quota", "rate limit", "resource_exhausted", "429"))


class GeminiTextProvider(BaseLLMProvider):
    """
    Concrete LLM provider backed by the Google Gemini generative API.

    Supports multiple API keys with automatic rotation on quota/rate-limit errors.
    Wraps only text-generation endpoints. Vision/multimodal capabilities
    remain in app/integrations/gemini_vision_service.py.
    """

    def __init__(self, api_keys: list[str], model: str) -> None:
        if not api_keys:
            raise RuntimeError(
                "No Gemini API keys provided. Set GEMINI_API_KEYS (comma-separated) "
                "or GEMINI_API_KEY in your .env file."
            )
        if not model:
            raise RuntimeError("GEMINI_MODEL is not set.")

        self._model = model
        # Build one client per key for clean key isolation
        self._clients: list[genai.Client] = [
            genai.Client(api_key=key.strip()) for key in api_keys if key.strip()
        ]
        self._num_keys = len(self._clients)
        self._current_key_index = 0
        logger.info(
            "GeminiTextProvider initialized: model=%s, keys=%d",
            model,
            self._num_keys,
        )

    # ------------------------------------------------------------------
    # Key rotation helpers
    # ------------------------------------------------------------------

    def _client(self) -> genai.Client:
        """Return the currently active client."""
        return self._clients[self._current_key_index]

    def _rotate_key(self) -> bool:
        """Rotate to the next key. Returns False if all keys exhausted."""
        next_index = (self._current_key_index + 1) % self._num_keys
        if next_index == self._current_key_index and self._num_keys > 1:
            return False  # already wrapped around
        if self._num_keys == 1:
            return False  # only one key, cannot rotate
        logger.warning(
            "GeminiTextProvider: key[%d] quota exhausted → rotating to key[%d]",
            self._current_key_index,
            next_index,
        )
        self._current_key_index = next_index
        return True

    async def _call_with_rotation(self, coro_factory) -> str:
        """
        Execute coro_factory(client) for each available key, rotating on quota errors.
        coro_factory receives the active genai.Client and returns a coroutine.
        """
        start_index = self._current_key_index
        attempts = 0
        while attempts < self._num_keys:
            try:
                return await coro_factory(self._client())
            except Exception as exc:
                if _is_quota_error(exc) and self._num_keys > 1:
                    rotated = self._rotate_key()
                    if not rotated or self._current_key_index == start_index:
                        raise RuntimeError(
                            f"All {self._num_keys} Gemini API keys are quota-exhausted. "
                            "Add more keys to GEMINI_API_KEYS."
                        ) from exc
                    attempts += 1
                    continue
                # Non-quota error — normalize and re-raise
                if isinstance(exc, errors.APIError):
                    raise RuntimeError(
                        f"Gemini API error ({exc.code}): {exc.message}"
                    ) from exc
                if isinstance(exc, asyncio.TimeoutError):
                    raise RuntimeError("Gemini request timed out") from exc
                raise RuntimeError(f"Gemini request failed: {exc}") from exc
        raise RuntimeError(
            f"All {self._num_keys} Gemini API keys are quota-exhausted. "
            "Add more keys to GEMINI_API_KEYS."
        )

    # ------------------------------------------------------------------
    # BaseLLMProvider interface
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        prompt = f"{system_prompt}\n\nUser:\n{user_prompt}"
        return await self._call_with_rotation(
            lambda client: self._raw_call(
                client, prompt, temperature=temperature, max_tokens=max_tokens
            )
        )

    async def chat(
        self,
        system_prompt: str,
        history: list[dict],
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        conversation = system_prompt + "\n\n"
        for message in history:
            role = "User" if message.get("role") == "user" else "Assistant"
            conversation += f"{role}: {message.get('content', '')}\n"
        conversation += f"User: {user_prompt}"
        return await self._call_with_rotation(
            lambda client: self._raw_call(
                client, conversation, temperature=temperature, max_tokens=max_tokens
            )
        )

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        prompt = f"{system_prompt}\n\nUser:\n{user_prompt}"

        async def _do(client: genai.Client) -> str:
            try:
                response = await client.aio.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                    ),
                )
            except Exception:
                raise  # Let _call_with_rotation handle it
            return self._extract_text(response)

        return await self._call_with_rotation(_do)

    async def summarize(
        self,
        text: str,
        *,
        max_tokens: int = 512,
    ) -> str:
        prompt = (
            "Summarize the following text concisely in a few sentences. "
            "Preserve all key facts. Output only the summary.\n\n"
            f"{text}"
        )
        return await self._call_with_rotation(
            lambda client: self._raw_call(
                client, prompt, temperature=0.3, max_tokens=max_tokens
            )
        )

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        # Gemini streaming not implemented — fall back to full generate() as single chunk.
        result = await self.generate(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        yield result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _raw_call(
        self,
        client: genai.Client,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        response = await client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        return self._extract_text(response)

    @staticmethod
    def _extract_text(response: types.GenerateContentResponse) -> str:
        try:
            text = response.text
        except Exception as exc:
            raise RuntimeError("Gemini returned no usable text in its response") from exc

        if not text or not text.strip():
            finish_reason = (
                getattr(response.candidates[0], "finish_reason", None)
                if response.candidates
                else None
            )
            raise RuntimeError(
                f"Gemini returned an empty response (finish_reason={finish_reason})"
            )
        return text.strip()
