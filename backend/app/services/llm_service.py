"""
LLMService for SmartTrip AI.

The single orchestration layer between the application (cognitive engines,
routes, services) and the provider layer (GroqProvider).

Responsibilities:
  - JSON generation with single-call parse (NO retry on parse failure)
  - Retry ONLY for genuine transient API failures (429, 503, timeout)
    — maximum ONE retry for each of those failure classes
  - Respect Retry-After when present in 429 errors
  - Circuit breaker to prevent cascading failures
  - Structured logging (provider, model, latency, tokens, retries, errors)
  - Streaming with automatic fallback

Retry policy (enforced here, not in the provider):
  - 429 rate-limit:  wait for Retry-After if present; max 1 retry
  - 503 unavailable: fixed 2s backoff; max 1 retry
  - timeout:         1 retry immediately
  - JSON parse fail: NO retry (the model already gave its best; retrying
                     wastes quota and would likely produce the same result)
  - empty response:  NO retry
  - finish_reason=length: NO retry (token budget is the constraint)

JSON cleaning (think-tag removal, fence stripping, first-object extraction)
is done inside GroqProvider.generate_json() before this layer ever sees the
text. A JSONDecodeError here means the response was unrecoverable.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import AsyncIterator

from app.services.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Circuit-breaker constants
# -----------------------------------------------------------------------
_CIRCUIT_FAILURE_THRESHOLD = 5   # consecutive failures before opening
_CIRCUIT_RESET_SECONDS = 60      # seconds before half-open attempt

# -----------------------------------------------------------------------
# Retry policy
# -----------------------------------------------------------------------
# Only these substrings in a RuntimeError message trigger a retry.
# "parse failure", "empty response", "truncated" are intentionally absent
# so that those errors propagate immediately without a second API call.
_RETRYABLE_PHRASES = (
    "rate limit",
    "429",
    "503",
    "service unavailable",
    "overloaded",
    "timeout",
    "connection",
)

_MAX_API_RETRIES = 1          # max 1 retry for transient API failures
_DEFAULT_RETRY_BACKOFF = 2.0  # seconds when no Retry-After header
_MAX_RETRY_AFTER = 30.0       # cap on Retry-After honour to avoid hanging


class _CircuitBreaker:
    """
    Lightweight circuit breaker.

    States: CLOSED (normal) → OPEN (rejecting) → HALF-OPEN (testing).
    Resets automatically after _CIRCUIT_RESET_SECONDS.
    """

    def __init__(self) -> None:
        self._failures = 0
        self._opened_at: float | None = None

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= _CIRCUIT_FAILURE_THRESHOLD:
            if self._opened_at is None:
                self._opened_at = time.monotonic()
                logger.error(
                    "LLMService circuit breaker OPENED after %d consecutive failures.",
                    self._failures,
                )

    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        elapsed = time.monotonic() - self._opened_at
        if elapsed >= _CIRCUIT_RESET_SECONDS:
            logger.info(
                "LLMService circuit breaker HALF-OPEN — attempting reset after %.0fs.",
                elapsed,
            )
            self._opened_at = None
            return False
        return True


_circuit_breaker = _CircuitBreaker()


class LLMService:
    """
    Orchestration service for all LLM text generation in SmartTrip AI.

    Constructed with a BaseLLMProvider instance (injected via FastAPI deps).
    The active provider is GroqProvider (Groq Inference API → qwen/qwen3.6-27b).

    Per-operation max_tokens defaults (override at call site):
        chat / QA:       1024
        diary / general: 2048
        itinerary JSON:  6000   (set in planning_engine.py)
    """

    def __init__(self, provider: BaseLLMProvider) -> None:
        self._provider = provider

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Generate a plain text response with retry and circuit-breaker."""
        return await self._execute_with_retry(
            "generate",
            self._provider.generate,
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
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
        """Multi-turn chat completion with retry and circuit-breaker."""
        return await self._execute_with_retry(
            "chat",
            self._provider.chat,
            system_prompt,
            history,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> dict:
        """
        Generate and parse a JSON object response.

        Calls the provider's generate_json() which performs ALL cleaning
        (think-tag removal, fence stripping, first-object extraction)
        and returns a clean JSON string.

        This method then does a single json.loads() on that string.

        Retry policy:
          - Transient API failures (429, 503, timeout) → retried by
            _execute_with_retry (max 1 retry, honours Retry-After on 429).
          - JSONDecodeError after provider cleaning → raised immediately
            as RuntimeError. NO second API call is issued. The model
            already returned its best attempt; retrying would consume
            additional quota and likely produce the same (broken) result.
          - Empty response → raised immediately (no retry).
          - finish_reason=length → raised by provider immediately (no retry).

        Raises:
            RuntimeError: On provider API errors, or if the cleaned
                          response is not valid JSON.
        """
        if _circuit_breaker.is_open():
            raise RuntimeError(
                "LLM service circuit breaker is open due to repeated failures. "
                "Please try again later."
            )

        start = time.monotonic()
        try:
            cleaned = await self._execute_with_retry(
                "generate_json",
                self._provider.generate_json,
                system_prompt,
                user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except RuntimeError:
            raise  # already logged and circuit-breaker handled

        logger.debug(
            "generate_json received from provider | provider=%s model=%s "
            "cleaned_preview=%.200r",
            self._provider.provider_name,
            self._provider.model_name,
            cleaned,
        )

        # Single json.loads() — NO retry on parse failure.
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            elapsed = time.monotonic() - start
            _circuit_breaker.record_failure()
            logger.error(
                "generate_json parse failure (NO retry) | provider=%s model=%s "
                "latency=%.3fs error=%s cleaned_preview=%.200r",
                self._provider.provider_name,
                self._provider.model_name,
                elapsed,
                exc,
                cleaned,
            )
            raise RuntimeError(
                f"LLM returned unparseable JSON after local cleaning. "
                f"Provider={self._provider.provider_name} "
                f"model={self._provider.model_name}. "
                f"Parse error: {exc}. "
                f"Cleaned preview: {cleaned[:200]!r}"
            ) from exc

        elapsed = time.monotonic() - start
        _circuit_breaker.record_success()
        logger.info(
            "generate_json succeeded | provider=%s model=%s latency=%.3fs",
            self._provider.provider_name,
            self._provider.model_name,
            elapsed,
        )
        return result

    async def summarize(
        self,
        text: str,
        *,
        max_tokens: int = 512,
    ) -> str:
        """Summarize text with retry and circuit-breaker."""
        return await self._execute_with_retry(
            "summarize",
            self._provider.summarize,
            text,
            max_tokens=max_tokens,
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
        Stream generated text.

        The provider's stream() already handles fallback to full generate()
        if streaming is unsupported. This method adds circuit-breaker
        protection at the service layer.
        """
        if _circuit_breaker.is_open():
            raise RuntimeError(
                "LLM service circuit breaker is open due to repeated failures. "
                "Please try again later."
            )
        start = time.monotonic()
        try:
            async for chunk in self._provider.stream(
                system_prompt, user_prompt,
                temperature=temperature, max_tokens=max_tokens,
            ):
                yield chunk
            _circuit_breaker.record_success()
        except RuntimeError:
            _circuit_breaker.record_failure()
            raise
        finally:
            elapsed = time.monotonic() - start
            logger.debug(
                "stream completed | provider=%s model=%s latency=%.3fs",
                self._provider.provider_name,
                self._provider.model_name,
                elapsed,
            )

    # ------------------------------------------------------------------
    # Internal: retry + circuit breaker + logging
    # ------------------------------------------------------------------

    async def _execute_with_retry(
        self,
        operation: str,
        fn,
        *args,
        **kwargs,
    ):
        """
        Call `fn(*args, **kwargs)` with circuit-breaker protection and a
        maximum of ONE retry for transient API failures.

        Retry criteria:
          - The error message contains one of _RETRYABLE_PHRASES.
          - The operation has not already been retried.

        On 429 errors, extracts the wait time from the error message
        (logged by GroqProvider) and sleeps for min(retry_after, 30s)
        before the single retry attempt.

        Non-retryable errors (parse failure, empty response, truncated
        output) propagate immediately without any sleep or second call.
        """
        if _circuit_breaker.is_open():
            raise RuntimeError(
                "LLM service circuit breaker is open due to repeated failures. "
                "Please try again later."
            )

        last_error: RuntimeError | None = None
        prompt_len = _estimate_prompt_length(args)

        for attempt in range(1, _MAX_API_RETRIES + 2):  # 1, 2
            start = time.monotonic()
            try:
                result = await fn(*args, **kwargs)
                elapsed = time.monotonic() - start
                _circuit_breaker.record_success()
                logger.info(
                    "%s succeeded | provider=%s model=%s attempt=%d "
                    "latency=%.3fs prompt_chars=%d response_chars=%d",
                    operation,
                    self._provider.provider_name,
                    self._provider.model_name,
                    attempt,
                    elapsed,
                    prompt_len,
                    len(result) if isinstance(result, str) else 0,
                )
                return result

            except RuntimeError as exc:
                elapsed = time.monotonic() - start
                last_error = exc
                error_text = str(exc).lower()
                is_retryable = any(
                    phrase in error_text for phrase in _RETRYABLE_PHRASES
                )

                logger.warning(
                    "%s failed (attempt %d/%d) | provider=%s model=%s "
                    "latency=%.3fs retryable=%s error=%s",
                    operation,
                    attempt,
                    _MAX_API_RETRIES + 1,
                    self._provider.provider_name,
                    self._provider.model_name,
                    elapsed,
                    is_retryable,
                    exc,
                )

                # If not retryable or we've exhausted retries, break now.
                if not is_retryable or attempt >= _MAX_API_RETRIES + 1:
                    break

                # Determine wait time.
                # On 429, the error message from GroqProvider contains
                # "retry_after=Xs" — extract that value.
                backoff = _DEFAULT_RETRY_BACKOFF
                if "429" in str(exc) or "rate limit" in error_text:
                    extracted = _extract_retry_after(str(exc))
                    if extracted is not None:
                        backoff = min(extracted, _MAX_RETRY_AFTER)
                        logger.info(
                            "%s: 429 rate limit — honouring Retry-After=%.1fs "
                            "(attempt %d → %d)",
                            operation, backoff, attempt, attempt + 1,
                        )
                    else:
                        logger.info(
                            "%s: 429 rate limit — no Retry-After header, "
                            "waiting %.1fs (attempt %d → %d)",
                            operation, backoff, attempt, attempt + 1,
                        )
                else:
                    logger.info(
                        "%s retrying in %.1fs (attempt %d → %d)",
                        operation, backoff, attempt, attempt + 1,
                    )

                await asyncio.sleep(backoff)

        _circuit_breaker.record_failure()
        logger.error(
            "%s exhausted all retries | provider=%s model=%s error=%s",
            operation,
            self._provider.provider_name,
            self._provider.model_name,
            last_error,
        )
        raise last_error  # type: ignore[misc]


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _extract_retry_after(error_message: str) -> float | None:
    """
    Extract the retry_after value (in seconds) from a 429 error message.

    GroqProvider._normalize_status_error() embeds the value as:
        "retry_after=<value>s"

    Returns None if the pattern is not found or the value is not numeric.
    """
    match = re.search(r"retry_after=(\d+(?:\.\d+)?)s?", error_message, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return None


def _estimate_prompt_length(args: tuple) -> int:
    """Estimate total character length of all string arguments for logging."""
    total = 0
    for arg in args:
        if isinstance(arg, str):
            total += len(arg)
        elif isinstance(arg, list):
            for item in arg:
                if isinstance(item, str):
                    total += len(item)
                elif isinstance(item, dict):
                    total += len(str(item))
    return total
