"""
LLMService for SmartTrip AI.

The single orchestration layer between the application (cognitive engines,
routes, services) and the provider layer (GroqProvider).

Responsibilities:
  - Prompt construction
  - JSON generation with validation and retry
  - Retry with exponential backoff for transient failures (429, 503)
  - Circuit breaker to prevent cascading failures
  - Structured logging (provider, model, latency, tokens, retries, errors)
  - Streaming with automatic fallback

Does NOT contain provider-specific logic. All provider calls go through
BaseLLMProvider. The active provider is GroqProvider (Groq → qwen/qwen3-32b).
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

        Calls the provider's generate_json(), validates the response as
        JSON, and retries once on a parse failure before raising.

        Raises:
            RuntimeError: If the response is not valid JSON after retry,
                          or on provider errors.
        """
        if _circuit_breaker.is_open():
            raise RuntimeError(
                "LLM service circuit breaker is open due to repeated failures. "
                "Please try again later."
            )

        attempt = 0
        last_error: Exception | None = None
        raw: str = ""

        while attempt <= 1:  # original attempt + 1 parse-failure retry
            start = time.monotonic()
            try:
                raw = await self._execute_with_retry(
                    "generate_json",
                    self._provider.generate_json,
                    system_prompt,
                    user_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except RuntimeError as exc:
                raise  # propagate provider errors immediately

            # Strip markdown fences if the model wrapped JSON in ```json ... ```
            cleaned = _strip_json_fences(raw)

            try:
                result = json.loads(cleaned)
                elapsed = time.monotonic() - start
                logger.debug(
                    "generate_json succeeded | provider=%s model=%s "
                    "attempt=%d latency=%.3fs",
                    self._provider.provider_name,
                    self._provider.model_name,
                    attempt + 1,
                    elapsed,
                )
                _circuit_breaker.record_success()
                return result
            except json.JSONDecodeError as exc:
                last_error = exc
                logger.warning(
                    "generate_json parse failure (attempt %d/2) | "
                    "provider=%s model=%s | raw_preview=%.120r",
                    attempt + 1,
                    self._provider.provider_name,
                    self._provider.model_name,
                    raw,
                )
                attempt += 1

        _circuit_breaker.record_failure()
        raise RuntimeError(
            f"LLM did not return valid JSON after 2 attempts. "
            f"Provider={self._provider.provider_name} model={self._provider.model_name}. "
            f"Last parse error: {last_error}. "
            f"Raw response preview: {raw[:200]!r}"
        )

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

def _strip_json_fences(text: str) -> str:
    """
    Remove markdown code fences that some models wrap around JSON output.

    Handles:  ```json\n{...}\n```  and  ```\n{...}\n```
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Remove first line (```json or ```) and last line (```)
        inner_lines = lines[1:] if lines[0].startswith("```") else lines
        if inner_lines and inner_lines[-1].strip() == "```":
            inner_lines = inner_lines[:-1]
        stripped = "\n".join(inner_lines).strip()
    return stripped


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
