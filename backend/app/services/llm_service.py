"""
LLMService for SmartTrip AI.

The single orchestration layer between the application (cognitive engines,
routes, services) and the provider layer (GroqProvider).

Responsibilities:
  - JSON generation with single-call parse (no retry on parse failure)
  - Retry with exponential backoff ONLY for genuine API failures (429, 503, timeout)
  - Circuit breaker to prevent cascading failures
  - Structured logging (provider, model, latency, tokens, retries, errors)
  - Streaming with automatic fallback

JSON cleaning (think-tag removal, fence stripping, first-object extraction)
is done inside GroqProvider.generate_json() before this layer ever sees the
text. A JSONDecodeError here means the response was unrecoverable — no API
retry is issued, because a second call would produce the same reasoning prefix.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator

from app.services.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Retry / circuit-breaker constants
# -----------------------------------------------------------------------
_RETRYABLE_PHRASES = ("rate limit", "429", "503", "unavailable", "overloaded", "timeout")
_MAX_RETRIES = 2               # total attempts = 1 original + _MAX_RETRIES
_BACKOFF_BASE = 1.5            # seconds; doubled on each retry
_CIRCUIT_FAILURE_THRESHOLD = 5 # consecutive failures before opening circuit
_CIRCUIT_RESET_SECONDS = 60    # seconds before attempting to close circuit


class _CircuitBreaker:
    """
    Lightweight circuit breaker for the LLM service layer.

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
            self._opened_at = None  # move to half-open: allow one attempt
            return False
        return True


_circuit_breaker = _CircuitBreaker()


class LLMService:
    """
    Orchestration service for all LLM text generation in SmartTrip AI.

    Constructed with a BaseLLMProvider instance (injected via FastAPI deps).
    The active provider is GroqProvider (Groq Inference API → qwen/qwen3-32b).

    Usage (via FastAPI dependency):
        llm: LLMService = Depends(get_llm_service)
        result = await llm.generate(system_prompt, user_prompt)
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
        max_tokens: int = 2048,
    ) -> str:
        """Generate a plain text response with retry and circuit-breaker protection."""
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
        max_tokens: int = 2048,
    ) -> str:
        """Multi-turn chat completion with retry and circuit-breaker protection."""
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
        max_tokens: int = 4096,
    ) -> dict:
        """
        Generate a JSON object response.

        Calls the provider's generate_json(), which performs ALL local
        cleaning before returning (think-tag removal, fence stripping,
        first-JSON-object extraction). This method then does a single
        json.loads() on the cleaned string.

        Retry policy:
          - API failures (429, timeout, 503) → retried by _execute_with_retry
            with exponential backoff.
          - JSONDecodeError after cleaning → raised immediately as RuntimeError.
            No second API call is issued: the model already returned its best
            attempt; retrying would produce the same reasoning prefix.

        Raises:
            RuntimeError: On provider API errors, or if the cleaned response
                          is not valid JSON.
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
            raise  # API errors already logged and circuit-breaker handled

        logger.debug(
            "generate_json received from provider | provider=%s model=%s "
            "cleaned_preview=%.200r",
            self._provider.provider_name,
            self._provider.model_name,
            cleaned,
        )

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            elapsed = time.monotonic() - start
            _circuit_breaker.record_failure()
            logger.error(
                "generate_json parse failure | provider=%s model=%s "
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
        logger.debug(
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
        """Summarize text with retry and circuit-breaker protection."""
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
        max_tokens: int = 2048,
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
        Call `fn(*args, **kwargs)` with exponential-backoff retry for
        transient failures (rate limits, service unavailable) and
        circuit-breaker protection.
        """
        if _circuit_breaker.is_open():
            raise RuntimeError(
                "LLM service circuit breaker is open due to repeated failures. "
                "Please try again later."
            )

        last_error: RuntimeError | None = None
        prompt_len = _estimate_prompt_length(args)

        for attempt in range(1, _MAX_RETRIES + 2):  # attempts: 1, 2, 3
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
                is_retryable = any(phrase in str(exc).lower() for phrase in _RETRYABLE_PHRASES)

                logger.warning(
                    "%s failed (attempt %d/%d) | provider=%s model=%s "
                    "latency=%.3fs retryable=%s error=%s",
                    operation,
                    attempt,
                    _MAX_RETRIES + 1,
                    self._provider.provider_name,
                    self._provider.model_name,
                    elapsed,
                    is_retryable,
                    exc,
                )

                if not is_retryable or attempt >= _MAX_RETRIES + 1:
                    break

                backoff = _BACKOFF_BASE * (2 ** (attempt - 1))
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
