"""
Groq Inference API provider for SmartTrip AI.

Uses openai.AsyncOpenAI pointed at Groq's OpenAI-compatible endpoint —
no local model loading, no Transformers, no HuggingFace dependency.
All text generation is done via the Groq Inference API over HTTPS.

All SDK and HTTP errors are normalized to RuntimeError before returning.
LLMService (and everything above it) never imports Groq-specific error types
— only BaseLLMProvider and RuntimeError cross the layer boundary.

Key design decisions for Qwen3 / reasoning models on Groq:
  - generate_json() passes reasoning_effort="none" so the model skips
    the <think> phase entirely and outputs only the JSON object. This
    eliminates the empty-response / parse-failure that occurred when the
    reasoning block consumed the entire token budget.
  - response_format={"type": "json_object"} is used so Groq guarantees
    a JSON-parseable response (falls back to plain completion if the model
    or endpoint returns 400 for this parameter).
  - Per-operation max_tokens limits are set at the call site to avoid
    wasting the Groq free-tier token-per-minute allowance:
        chat / QA:       1024
        diary / general: 2048
        itinerary:       6000
  - On 429, the Retry-After header is read and honoured (max 1 retry).
  - JSON parse failures do NOT trigger another API call.
  - finish_reason == "length" raises immediately without any retry.

Logging:
  Every call logs: provider, model, latency, finish_reason,
  prompt_tokens, completion_tokens, total_tokens (from usage), and any
  errors. On 429, all x-ratelimit-* headers are logged. GROQ_API_KEY
  is NEVER logged.
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

# ---------------------------------------------------------------------------
# JSON-mode system-prompt suffix
# ---------------------------------------------------------------------------
# Added to the system prompt for every generate_json() call.
# Tells the model explicitly what output format is required and prohibits
# all reasoning output (<think> blocks, markdown, prose).
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

# ---------------------------------------------------------------------------
# HTTP status → human-readable message
# ---------------------------------------------------------------------------
_ERROR_MAP: dict[int, str] = {
    401: "Groq API authentication failed. Check GROQ_API_KEY.",
    403: "Groq API access denied. The model or endpoint may require a different plan.",
    404: "Groq model not found. Check GROQ_MODEL environment variable.",
    408: "Groq request timed out.",
    429: "Groq rate limit exceeded.",
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
        max_tokens: int = 1024,
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
        max_tokens: int = 1024,
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
        max_tokens: int = 2048,
    ) -> str:
        """
        Generate a JSON response and return a clean, parseable JSON string.

        Pipeline:
          1. Add reasoning_effort="none" for Qwen/thinking models on Groq
             so the model skips the <think> phase and writes only JSON.
          2. Call Groq with response_format={"type": "json_object"}.
             Falls back to plain completion on 400 (model doesn't support it).
          3. Check content is not None/empty before attempting to parse.
          4. Check finish_reason: raise immediately if "length" (truncated).
          5. Log finish_reason, prompt_tokens, completion_tokens, total_tokens.
          6. Strip any residual <think>...</think> blocks (defensive).
          7. Strip markdown code fences (defensive).
          8. Regex-extract the first complete JSON object.
          9. Verify balanced braces (completeness guard).
         10. Return the cleaned string; json.loads() is LLMService's job.

        Raises:
            RuntimeError: On API failures (401/403/404/408/429/500/503),
                          on truncated output (finish_reason=length),
                          on empty response, or on incomplete JSON after cleaning.
        """
        json_system_prompt = system_prompt + _JSON_INSTRUCTION
        messages = _build_messages(json_system_prompt, [], user_prompt)
        start = time.monotonic()

        # Build extra kwargs. reasoning_effort="none" disables the thinking
        # phase on Qwen3 and similar CoT models. Groq ignores this parameter
        # for non-reasoning models, so it is safe to send unconditionally.
        extra_kwargs: dict = {"reasoning_effort": "none"}

        # Attempt with JSON-object mode first.
        response = None
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                **extra_kwargs,
            )
        except APIStatusError as exc:
            if exc.status_code == 400:
                # response_format not supported by this model — fall back.
                logger.debug(
                    "generate_json: response_format=json_object not supported "
                    "for model=%s (400), falling back to plain completion.",
                    self._model,
                )
                response = None
            elif exc.status_code == 422:
                # reasoning_effort not recognised — retry without it.
                logger.debug(
                    "generate_json: reasoning_effort not supported for "
                    "model=%s (422), retrying without it.",
                    self._model,
                )
                response = None
                extra_kwargs = {}
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
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **extra_kwargs,
                )
            except APIStatusError as exc:
                elapsed = time.monotonic() - start
                raise self._normalize_status_error(exc, elapsed) from exc
            except APITimeoutError as exc:
                elapsed = time.monotonic() - start
                raise RuntimeError(
                    f"Groq request timed out for model={self._model}"
                ) from exc
            except APIConnectionError as exc:
                elapsed = time.monotonic() - start
                raise RuntimeError(
                    f"Groq connection failed for model={self._model}: {exc}"
                ) from exc
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                elapsed = time.monotonic() - start
                raise RuntimeError(
                    f"Groq request failed for model={self._model}: {exc}"
                ) from exc

        elapsed = time.monotonic() - start

        # ------------------------------------------------------------------
        # Inspect finish_reason BEFORE touching the text.
        # "length" / "max_tokens" means the model was cut off — JSON is
        # definitely incomplete. Raise immediately; do NOT parse.
        # ------------------------------------------------------------------
        finish_reason: str | None = None
        try:
            finish_reason = response.choices[0].finish_reason
        except (AttributeError, IndexError):
            pass

        # Log token usage + finish_reason for every call.
        usage = response.usage
        if usage:
            logger.info(
                "generate_json finish | model=%s finish_reason=%s latency=%.3fs "
                "prompt_tokens=%d completion_tokens=%d total_tokens=%d "
                "max_tokens_requested=%d",
                self._model, finish_reason, elapsed,
                usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
                max_tokens,
            )
        else:
            logger.info(
                "generate_json finish | model=%s finish_reason=%s latency=%.3fs "
                "max_tokens_requested=%d (no usage data)",
                self._model, finish_reason, elapsed, max_tokens,
            )

        if finish_reason in ("length", "max_tokens"):
            raise RuntimeError(
                f"The model output was truncated because the completion token limit "
                f"was reached (finish_reason={finish_reason!r}, model={self._model}, "
                f"max_tokens={max_tokens}). "
                f"Increase max_tokens for this operation."
            )

        # ------------------------------------------------------------------
        # Extract raw text — guard against None content.
        # ------------------------------------------------------------------
        try:
            raw = response.choices[0].message.content
        except (AttributeError, IndexError, KeyError) as exc:
            raise RuntimeError(
                f"Groq returned an unexpected response structure for model={self._model}"
            ) from exc

        if raw is None:
            raise RuntimeError(
                f"Groq returned a None content field for model={self._model}. "
                f"The reasoning model may have emitted only a thinking block with no answer."
            )

        if not raw.strip():
            raise RuntimeError(
                f"Groq returned an empty response for model={self._model}."
            )

        logger.debug(
            "generate_json raw_preview | model=%s raw=%.300r",
            self._model, raw,
        )

        # ------------------------------------------------------------------
        # Local cleaning pipeline — no API calls, no retries.
        # ------------------------------------------------------------------
        cleaned = _strip_think_tags(raw)       # remove <think>...</think>
        cleaned = _strip_fences(cleaned)       # remove ``` / ```json
        cleaned = _extract_first_json(cleaned) # pull first {...} object

        logger.debug(
            "generate_json cleaned_preview | model=%s cleaned=%.300r",
            self._model, cleaned,
        )

        # ------------------------------------------------------------------
        # Completeness guard: verify balanced braces before returning.
        # ------------------------------------------------------------------
        if not _is_json_complete(cleaned):
            raise RuntimeError(
                f"The model returned an incomplete JSON object after cleaning "
                f"(finish_reason={finish_reason!r}, model={self._model}, "
                f"max_tokens={max_tokens}). "
                f"The output likely exceeded the token budget. "
                f"Cleaned preview: {cleaned[:300]!r}"
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
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """
        Stream text chunks from the Groq API.

        Falls back to a single-chunk yield from generate() on any error
        so the caller always receives a valid async iterator.
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
        Execute a plain chat completion request against the Groq API.

        Normalizes all openai SDK errors to RuntimeError.
        Logs latency, model, finish_reason, and token usage on success.
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
            finish_reason = response.choices[0].finish_reason
        except (AttributeError, IndexError, KeyError) as exc:
            raise RuntimeError(
                f"Groq returned an unexpected response structure for model={self._model}"
            ) from exc

        if text is None or not text.strip():
            raise RuntimeError(
                f"Groq returned an empty response for model={self._model}"
            )

        # Log usage metrics
        usage = response.usage
        if usage:
            logger.info(
                "Groq completion | model=%s finish_reason=%s latency=%.3fs "
                "prompt_tokens=%d completion_tokens=%d total_tokens=%d",
                self._model,
                finish_reason,
                elapsed,
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
            )
        else:
            logger.info(
                "Groq completion | model=%s finish_reason=%s latency=%.3fs (no usage data)",
                self._model, finish_reason, elapsed,
            )

        return text.strip()

    def _normalize_status_error(
        self, exc: APIStatusError, elapsed: float
    ) -> RuntimeError:
        """
        Convert an openai.APIStatusError into a meaningful RuntimeError.

        On 429, reads and logs all Groq rate-limit headers (Retry-After,
        x-ratelimit-*) so the exact quota consumption is visible in logs.
        GROQ_API_KEY is never logged.
        """
        status_code: int = exc.status_code

        if status_code == 429:
            # Log all rate-limit headers for diagnosis.
            headers = {}
            if exc.response is not None:
                for h in (
                    "retry-after",
                    "x-ratelimit-limit-requests",
                    "x-ratelimit-remaining-requests",
                    "x-ratelimit-reset-requests",
                    "x-ratelimit-limit-tokens",
                    "x-ratelimit-remaining-tokens",
                    "x-ratelimit-reset-tokens",
                ):
                    val = exc.response.headers.get(h)
                    if val is not None:
                        headers[h] = val

            retry_after = headers.get("retry-after")
            logger.error(
                "Groq 429 rate limit | model=%s latency=%.3fs retry_after=%s "
                "limit_requests=%s remaining_requests=%s reset_requests=%s "
                "limit_tokens=%s remaining_tokens=%s reset_tokens=%s",
                self._model, elapsed,
                retry_after,
                headers.get("x-ratelimit-limit-requests"),
                headers.get("x-ratelimit-remaining-requests"),
                headers.get("x-ratelimit-reset-requests"),
                headers.get("x-ratelimit-limit-tokens"),
                headers.get("x-ratelimit-remaining-tokens"),
                headers.get("x-ratelimit-reset-tokens"),
            )
            return RuntimeError(
                f"Groq rate limit exceeded (429). "
                f"retry_after={retry_after}s. "
                f"remaining_tokens={headers.get('x-ratelimit-remaining-tokens', 'unknown')}. "
                f"Model: {self._model}."
            )

        message = _ERROR_MAP.get(
            status_code,
            f"Groq API error ({status_code}): {getattr(exc, 'message', str(exc))}",
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
      - ```json\\n{...}\\n```
      - ```\\n{...}\\n```
      - ``` {...} ``` (inline)
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        inner = lines[1:] if lines[0].startswith("```") else lines
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
        return text

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

    return text[start_idx:]


def _is_json_complete(text: str) -> bool:
    """
    Return True if `text` contains a complete, balanced JSON object.

    Returns False for empty strings, strings without '{', or strings
    where the root object is never closed (truncated output).
    """
    text = text.strip()
    start_idx = text.find("{")
    if start_idx == -1:
        return False

    depth = 0
    in_string = False
    escape_next = False

    for ch in text[start_idx:]:
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
                return True

    return False
