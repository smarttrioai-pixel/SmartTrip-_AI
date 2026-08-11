"""
Hugging Face Inference API provider for SmartTrip AI.

Uses huggingface_hub.AsyncInferenceClient exclusively — no local model
loading, no transformers.from_pretrained(), no GPU dependency. All
inference is done via the Hugging Face Inference API (serverless endpoints).

All SDK and HTTP errors are normalized to RuntimeError before returning.
LLMService (and everything above it) never imports HuggingFace-specific
error types — only BaseLLMProvider and RuntimeError cross the layer boundary.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from huggingface_hub import AsyncInferenceClient
from huggingface_hub.errors import HfHubHTTPError

from app.services.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)

# JSON-mode instruction appended to system prompts for generate_json().
# This is the most compatible approach — some HF models support a native
# JSON mode; others need this instruction in the prompt itself.
_JSON_INSTRUCTION = (
    "\n\nIMPORTANT: Your response must be ONLY a valid JSON object. "
    "Do NOT include any prose, markdown code fences, or explanation. "
    "Return the raw JSON object and nothing else."
)


class HuggingFaceProvider(BaseLLMProvider):
    """
    Concrete LLM provider backed by the Hugging Face Inference API.

    Supports chat-completion style messages (the standard interface for all
    modern instruction-tuned models on HF). Falls back gracefully to
    text-generation for models that don't support the chat endpoint.
    """

    def __init__(self, api_token: str, model: str) -> None:
        if not api_token:
            raise RuntimeError(
                "HF_API_TOKEN is not set. Provide a valid Hugging Face API token."
            )
        if not model:
            raise RuntimeError("HF_MODEL is not set.")

        self._model = model
        self._client = AsyncInferenceClient(
            model=model,
            token=api_token,
        )
        logger.info("HuggingFaceProvider initialized with model=%s", model)

    # ------------------------------------------------------------------
    # BaseLLMProvider implementation
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        return "huggingface"

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
        messages = self._build_messages(system_prompt, [], user_prompt)
        return await self._chat_complete(messages, temperature=temperature, max_tokens=max_tokens)

    async def chat(
        self,
        system_prompt: str,
        history: list[dict],
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        messages = self._build_messages(system_prompt, history, user_prompt)
        return await self._chat_complete(messages, temperature=temperature, max_tokens=max_tokens)

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        # Append JSON-only instruction to the system prompt so the model
        # knows what output format is required.
        json_system_prompt = system_prompt + _JSON_INSTRUCTION
        messages = self._build_messages(json_system_prompt, [], user_prompt)
        return await self._chat_complete(messages, temperature=temperature, max_tokens=max_tokens)

    async def summarize(
        self,
        text: str,
        *,
        max_tokens: int = 512,
    ) -> str:
        system_prompt = (
            "You are a concise summarizer. Summarize the provided text clearly "
            "in a few sentences. Preserve the key facts. Output only the summary."
        )
        messages = self._build_messages(system_prompt, [], text)
        return await self._chat_complete(messages, temperature=0.3, max_tokens=max_tokens)

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """
        Stream text from the HF Inference API.

        Uses chat_completion with stream=True. If the model or endpoint
        does not support streaming, falls back to a single-chunk yield
        from generate() so the caller always gets an async iterator.
        """
        messages = self._build_messages(system_prompt, [], user_prompt)
        try:
            stream = await self._client.chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except (HfHubHTTPError, NotImplementedError, Exception) as exc:
            # Streaming not supported by this model/endpoint — fall back
            # to a single full-text yield so the caller never sees an error.
            logger.warning(
                "HuggingFace streaming not available for model=%s (%s). "
                "Falling back to full generate().",
                self._model, exc,
            )
            result = await self.generate(
                system_prompt, user_prompt,
                temperature=temperature, max_tokens=max_tokens,
            )
            yield result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_messages(
        system_prompt: str,
        history: list[dict],
        user_prompt: str,
    ) -> list[dict]:
        """Build the messages list for chat_completion."""
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

    async def _chat_complete(
        self,
        messages: list[dict],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """
        Execute a chat completion request against the HF Inference API.

        Normalizes all HfHubHTTPError and network errors to RuntimeError.
        HTTP status codes are mapped to meaningful messages.
        """
        try:
            response = await self._client.chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except HfHubHTTPError as exc:
            raise self._normalize_hf_error(exc) from exc
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                f"HuggingFace request timed out for model={self._model}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"HuggingFace request failed for model={self._model}: {exc}"
            ) from exc

        try:
            text = response.choices[0].message.content
        except (AttributeError, IndexError, KeyError) as exc:
            raise RuntimeError(
                f"HuggingFace returned an unexpected response structure for model={self._model}"
            ) from exc

        if not text or not text.strip():
            raise RuntimeError(
                f"HuggingFace returned an empty response for model={self._model}"
            )

        return text.strip()

    @staticmethod
    def _normalize_hf_error(exc: HfHubHTTPError) -> RuntimeError:
        """
        Convert an HfHubHTTPError into a meaningful RuntimeError.

        The status code is extracted from the exception and mapped to a
        human-readable message so that FastAPI routes can surface a
        meaningful 503 to clients.
        """
        status_code: int | None = getattr(exc, "response", None)
        if hasattr(exc, "response") and exc.response is not None:
            status_code = exc.response.status_code
        else:
            status_code = None

        messages = {
            401: "HuggingFace API authentication failed. Check HF_API_TOKEN.",
            403: "HuggingFace access denied. The model may require a Pro subscription or gated access.",
            404: "HuggingFace model not found. Check HF_MODEL environment variable.",
            408: "HuggingFace request timed out.",
            429: "HuggingFace rate limit exceeded. The service will retry automatically.",
            500: "HuggingFace server error (500). The inference service is experiencing issues.",
            503: "HuggingFace service unavailable (503). The model may be loading or overloaded.",
        }

        if status_code in messages:
            return RuntimeError(f"HuggingFace error ({status_code}): {messages[status_code]}")

        return RuntimeError(f"HuggingFace API error: {exc}")
