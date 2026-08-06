"""
Groq Inference API provider for SmartTrip AI.

Uses openai.AsyncOpenAI pointed at Groq's OpenAI-compatible endpoint —
no local model loading, no Transformers, no HuggingFace dependency.
All text generation is done via the Groq Inference API over HTTPS.

All SDK and HTTP errors are normalized to RuntimeError before returning.
LLMService (and everything above it) never imports Groq-specific error types
— only BaseLLMProvider and RuntimeError cross the layer boundary.

Logging:
  Every call logs: provider, model, latency, prompt_tokens, completion_tokens,
  total_tokens (from usage), and any errors.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator

from openai import AsyncOpenAI, APIStatusError, APITimeoutError, APIConnectionError

from app.services.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)

# JSON-mode instruction appended to system prompts for generate_json().
_JSON_INSTRUCTION = (
    "\n\nIMPORTANT: Your response must be ONLY a valid JSON object. "
    "Do NOT include any prose, markdown code fences, or explanation. "
    "Return the raw JSON object and nothing else."
)

# Map Groq/OpenAI HTTP status codes to human-readable RuntimeError messages.
_ERROR_MAP: dict[int, str] = {
    401: "Groq API authentication failed. Check GROQ_API_KEY.",
    403: "Groq API access denied. The model or endpoint may require a different plan.",
    404: "Groq model not found. Check GROQ_MODEL environment variable.",
    408: "Groq request timed out.",
    429: "Groq rate limit exceeded. The service will retry automatically.",
    500: "Groq server error (500). The inference service is experiencing issues.",
    503: "Groq service unavailable (503). The model may be overloaded.",
}


class GroqProvider(BaseLLMProvider):
    """
    Concrete LLM provider backed by the Groq Inference API.

    Uses Groq's OpenAI-compatible REST endpoint via the openai SDK.
    Supports chat completion, JSON generation, streaming, and summarization.
    All SDK errors are normalized to RuntimeError.
    """

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Provide a valid Groq API key."
            )
        if not model:
            raise RuntimeError("GROQ_MODEL is not set.")

        self._model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        logger.info("GroqProvider initialized with model=%s", model)

    # ------------------------------------------------------------------
    # BaseLLMProvider implementation
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        return "groq"

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
        """Generate a plain text response via Groq chat completion."""
        messages = _build_messages(system_prompt, [], user_prompt)
        return await self._chat_complete(
            messages, temperature=temperature, max_tokens=max_tokens
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
        """Multi-turn conversational completion via Groq."""
        messages = _build_messages(system_prompt, history, user_prompt)
        return await self._chat_complete(
            messages, temperature=temperature, max_tokens=max_tokens
        )

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """
        Generate a response expected to be pure JSON.

        Augments the system prompt with a JSON-only instruction.
        The raw response string is returned; parsing and retry logic
        are the responsibility of LLMService.generate_json().
        """
        json_system_prompt = system_prompt + _JSON_INSTRUCTION
        messages = _build_messages(json_system_prompt, [], user_prompt)
        return await self._chat_complete(
            messages, temperature=temperature, max_tokens=max_tokens
        )

    async def summarize(
        self,
        text: str,
        *,
        max_tokens: int = 512,
    ) -> str:
        """Summarize the given text via Groq."""
        system_prompt = (
            "You are a concise summarizer. Summarize the provided text clearly "
            "in a few sentences. Preserve the key facts. Output only the summary."
        )
        messages = _build_messages(system_prompt, [], text)
        return await self._chat_complete(
            messages, temperature=0.3, max_tokens=max_tokens
        )

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """
        Stream text chunks from the Groq API.

        If streaming is unavailable (unexpected error), falls back to a
        single-chunk yield from generate() so the caller always receives
        a valid async iterator.
        """
        messages = _build_messages(system_prompt, [], user_prompt)
        start = time.monotonic()
        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
            elapsed = time.monotonic() - start
            logger.debug(
                "stream completed | provider=groq model=%s latency=%.3fs",
                self._model, elapsed,
            )
        except (APIStatusError, APITimeoutError, APIConnectionError, Exception) as exc:
            elapsed = time.monotonic() - start
            logger.warning(
                "Groq streaming not available for model=%s (%.3fs): %s. "
                "Falling back to full generate().",
                self._model, elapsed, exc,
            )
            result = await self.generate(
                system_prompt, user_prompt,
                temperature=temperature, max_tokens=max_tokens,
            )
            yield result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _chat_complete(
        self,
        messages: list[dict],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """
        Execute a chat completion request against the Groq API.

        Normalizes all openai SDK errors to RuntimeError.
        Logs latency, model, and token usage on success.
        """
        start = time.monotonic()
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except APIStatusError as exc:
            elapsed = time.monotonic() - start
            raise self._normalize_status_error(exc, elapsed) from exc
        except APITimeoutError as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "Groq request timed out | model=%s latency=%.3fs",
                self._model, elapsed,
            )
            raise RuntimeError(
                f"Groq request timed out for model={self._model}"
            ) from exc
        except APIConnectionError as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "Groq connection failed | model=%s latency=%.3fs error=%s",
                self._model, elapsed, exc,
            )
            raise RuntimeError(
                f"Groq connection failed for model={self._model}: {exc}"
            ) from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "Groq unexpected error | model=%s latency=%.3fs error=%s",
                self._model, elapsed, exc,
            )
            raise RuntimeError(
                f"Groq request failed for model={self._model}: {exc}"
            ) from exc

        elapsed = time.monotonic() - start

        try:
            text = response.choices[0].message.content
        except (AttributeError, IndexError, KeyError) as exc:
            raise RuntimeError(
                f"Groq returned an unexpected response structure for model={self._model}"
            ) from exc

        if not text or not text.strip():
            raise RuntimeError(
                f"Groq returned an empty response for model={self._model}"
            )

        # Log usage metrics
        usage = response.usage
        if usage:
            logger.info(
                "Groq completion | model=%s latency=%.3fs "
                "prompt_tokens=%d completion_tokens=%d total_tokens=%d",
                self._model,
                elapsed,
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
            )
        else:
            logger.info(
                "Groq completion | model=%s latency=%.3fs (no usage data)",
                self._model, elapsed,
            )

        return text.strip()

    def _normalize_status_error(
        self, exc: APIStatusError, elapsed: float
    ) -> RuntimeError:
        """
        Convert an openai.APIStatusError into a meaningful RuntimeError.

        Maps known HTTP status codes to human-readable messages.
        No traceback details from the SDK are leaked to callers.
        """
        status_code: int = exc.status_code
        message = _ERROR_MAP.get(
            status_code,
            f"Groq API error ({status_code}): {exc.message}",
        )
        logger.error(
            "Groq API error | model=%s status=%d latency=%.3fs message=%s",
            self._model, status_code, elapsed, message,
        )
        return RuntimeError(message)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _build_messages(
    system_prompt: str,
    history: list[dict],
    user_prompt: str,
) -> list[dict]:
    """Build the OpenAI-compatible messages list for chat completion."""
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_prompt})
    return messages
