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
import re
import time
from typing import AsyncIterator

from openai import AsyncOpenAI, APIStatusError, APITimeoutError, APIConnectionError

from app.services.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)

# JSON-mode instruction appended to system prompts for generate_json().
# Explicit prohibition of reasoning output for models that emit <think> blocks.
_JSON_INSTRUCTION = (
    "\n\n"
    "CRITICAL OUTPUT RULES:\n"
    "- Return ONLY a single valid JSON object.\n"
    "- Do NOT output <think> blocks, reasoning, or internal monologue.\n"
    "- Do NOT wrap output in markdown code fences (``` or ```json).\n"
    "- Do NOT include comments, prose, or any text before or after the JSON.\n"
    "- The very first character of your response must be '{'.\n"
    "- The very last character of your response must be '}'.\n"
    "- Output exactly one JSON object and nothing else."
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
        Generate a JSON response and return a clean, parseable JSON string.

        Pipeline (all local — no extra API calls on cleaning failures):
          1. Call Groq with response_format={"type": "json_object"} when supported.
          2. Strip <think>...</think> reasoning blocks from the raw response.
          3. Strip markdown code fences (```json / ```).
          4. Regex-extract the first complete JSON object if surrounding text remains.
          5. Log raw vs cleaned separately for debugging.
          6. Return the cleaned string. Parsing and circuit-breaking are
             the responsibility of LLMService.generate_json().

        Raises:
            RuntimeError: Only on genuine API failures (401/403/404/408/429/500/503).
                          Never raises for reasoning-prefix or formatting issues —
                          those are handled locally above.
        """
        json_system_prompt = system_prompt + _JSON_INSTRUCTION
        messages = _build_messages(json_system_prompt, [], user_prompt)
        start = time.monotonic()

        # Attempt 1: request JSON-object mode from the API (Groq supports this
        # for most models; if not supported the API returns a 400 which we catch).
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
        except APIStatusError as exc:
            if exc.status_code == 400:
                # response_format not supported for this model — fall back to
                # plain text completion with local cleaning below.
                logger.debug(
                    "generate_json: response_format=json_object not supported "
                    "for model=%s (400), falling back to plain completion.",
                    self._model,
                )
                response = None
            else:
                elapsed = time.monotonic() - start
                raise self._normalize_status_error(exc, elapsed) from exc
        except APITimeoutError as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "generate_json timed out | model=%s latency=%.3fs",
                self._model, elapsed,
            )
            raise RuntimeError(
                f"Groq request timed out for model={self._model}"
            ) from exc
        except APIConnectionError as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "generate_json connection failed | model=%s latency=%.3fs error=%s",
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
                "generate_json unexpected error | model=%s latency=%.3fs error=%s",
                self._model, elapsed, exc,
            )
            raise RuntimeError(
                f"Groq request failed for model={self._model}: {exc}"
            ) from exc

        # Fall back to plain completion if json_object mode was rejected.
        if response is None:
            response = await self._chat_complete(
                messages, temperature=temperature, max_tokens=max_tokens,
                _return_response=True,
            )

        elapsed = time.monotonic() - start

        # Extract raw text from response object.
        try:
            raw = response.choices[0].message.content or ""
        except (AttributeError, IndexError, KeyError) as exc:
            raise RuntimeError(
                f"Groq returned an unexpected response structure for model={self._model}"
            ) from exc

        if not raw.strip():
            raise RuntimeError(
                f"Groq returned an empty response for model={self._model}"
            )

        # Log usage and raw preview.
        usage = response.usage
        if usage:
            logger.info(
                "generate_json raw | model=%s latency=%.3fs "
                "prompt_tokens=%d completion_tokens=%d total_tokens=%d "
                "raw_preview=%.120r",
                self._model, elapsed,
                usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
                raw,
            )
        else:
            logger.info(
                "generate_json raw | model=%s latency=%.3fs raw_preview=%.120r",
                self._model, elapsed, raw,
            )

        # ------------------------------------------------------------------
        # Local cleaning pipeline — no API calls, no retries.
        # ------------------------------------------------------------------
        cleaned = _strip_think_tags(raw)   # remove <think>...</think> blocks
        cleaned = _strip_fences(cleaned)   # remove ``` / ```json wrappers
        cleaned = _extract_first_json(cleaned)  # pull first {...} object

        logger.debug(
            "generate_json cleaned | model=%s cleaned_preview=%.200r",
            self._model, cleaned,
        )

        return cleaned

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
        _return_response: bool = False,
    ) -> str:
        """
        Execute a plain chat completion request against the Groq API.

        Normalizes all openai SDK errors to RuntimeError.
        Logs latency, model, and token usage on success.
        When _return_response=True, returns the raw response object
        (used by generate_json fallback path only).
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

        if _return_response:
            return response  # type: ignore[return-value]
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


def _strip_think_tags(text: str) -> str:
    """
    Remove all <think>...</think> reasoning blocks emitted by Qwen3 and
    similar chain-of-thought models.

    Handles:
      - Multi-line think blocks
      - Multiple consecutive think blocks
      - Partial/unclosed think tags (removes from <think> to end-of-string)
    """
    # Remove complete <think>...</think> blocks (non-greedy, DOTALL).
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove any unclosed <think> block that runs to end of string.
    cleaned = re.sub(r"<think>.*$", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


def _strip_fences(text: str) -> str:
    """
    Remove markdown code fences that some models wrap around JSON output.

    Handles:
      - ```json\n{...}\n```
      - ```\n{...}\n```
      - ``` {...} ``` (inline)
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Drop the opening fence line (e.g. ```json or ```).
        inner = lines[1:] if lines[0].startswith("```") else lines
        # Drop the closing fence line if present.
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        stripped = "\n".join(inner).strip()
    return stripped


def _extract_first_json(text: str) -> str:
    """
    Extract the first complete JSON object {...} from text.

    Used as a last-resort safety net when the model emits surrounding
    prose despite explicit instructions. Walks the string character by
    character tracking brace depth to find the balanced outer object.

    Returns the original text unchanged if no object boundary is found,
    so LLMService.generate_json() can produce a meaningful parse error.
    """
    start_idx = text.find("{")
    if start_idx == -1:
        return text  # no JSON object found; let upstream handle the error

    depth = 0
    in_string = False
    escape_next = False

    for i, ch in enumerate(text[start_idx:], start=start_idx):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start_idx : i + 1]

    # Unbalanced braces — return from the first { to end and let upstream handle it.
    return text[start_idx:]
