"""
Gemini Text Provider for SmartTrip AI — TEXT generation only.

This provider wraps the Gemini generative API for text tasks.
It is included to make the provider layer complete and future-proof
(e.g. if a project-level decision restores Gemini for text on a subset
of tasks), but it is NOT the default provider.

The default provider is HuggingFace (LLM_PROVIDER=huggingface).

IMPORTANT: Gemini Vision (generate_json_from_image) is NOT part of this
provider. Vision stays in app/integrations/gemini_vision_service.py and
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


class GeminiTextProvider(BaseLLMProvider):
    """
    Concrete LLM provider backed by the Google Gemini generative API.

    Wraps only text-generation endpoints. Vision/multimodal capabilities
    remain in app/integrations/gemini_vision_service.py.
    """

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Cannot initialize GeminiTextProvider."
            )
        if not model:
            raise RuntimeError("GEMINI_MODEL is not set.")

        self._model = model
        self._client = genai.Client(api_key=api_key)
        logger.info("GeminiTextProvider initialized with model=%s", model)

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
        return await self._call(prompt, temperature=temperature, max_tokens=max_tokens)

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
        return await self._call(conversation, temperature=temperature, max_tokens=max_tokens)

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        prompt = f"{system_prompt}\n\nUser:\n{user_prompt}"
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
        except errors.APIError as exc:
            raise RuntimeError(f"Gemini API error ({exc.code}): {exc.message}") from exc
        except asyncio.TimeoutError as exc:
            raise RuntimeError("Gemini request timed out") from exc
        except Exception as exc:
            raise RuntimeError(f"Gemini request failed: {exc}") from exc

        return self._extract_text(response)

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
        return await self._call(prompt, temperature=0.3, max_tokens=max_tokens)

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        # Gemini streaming not implemented in this provider — fall back to
        # full generate() as a single chunk so the interface stays consistent.
        result = await self.generate(
            system_prompt, user_prompt,
            temperature=temperature, max_tokens=max_tokens,
        )
        yield result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
        except errors.APIError as exc:
            raise RuntimeError(f"Gemini API error ({exc.code}): {exc.message}") from exc
        except asyncio.TimeoutError as exc:
            raise RuntimeError("Gemini request timed out") from exc
        except Exception as exc:
            raise RuntimeError(f"Gemini request failed: {exc}") from exc

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
