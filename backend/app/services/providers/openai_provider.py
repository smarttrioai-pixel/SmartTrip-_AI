"""
OpenAI API provider for SmartTrip AI.

Uses openai.AsyncOpenAI for text generation.

All SDK and HTTP errors are normalized to RuntimeError before returning.
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

_ERROR_MAP: dict[int, str] = {
    401: "OpenAI API authentication failed. Check OPENAI_API_KEY.",
    403: "OpenAI API access denied.",
    404: "OpenAI model not found.",
    408: "OpenAI request timed out.",
    429: "OpenAI rate limit exceeded.",
    500: "OpenAI server error (500).",
    503: "OpenAI service unavailable (503).",
}

class OpenAIProvider(BaseLLMProvider):
    """
    Concrete LLM provider backed by the OpenAI API.
    """

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Provide a valid OpenAI API key.")
        if not model:
            raise RuntimeError("OpenAI model is not set.")

        self._model = model
        self._client = AsyncOpenAI(api_key=api_key)
        logger.info("OpenAIProvider initialized with model=%s", model)

    @property
    def provider_name(self) -> str:
        return "openai"

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
        json_system_prompt = system_prompt + _JSON_INSTRUCTION
        messages = _build_messages(json_system_prompt, [], user_prompt)
        start = time.monotonic()

        response = None
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
                logger.debug("generate_json: response_format=json_object not supported (400), falling back.")
                response = None
            else:
                elapsed = time.monotonic() - start
                raise self._normalize_status_error(exc, elapsed) from exc
        except APITimeoutError as exc:
            elapsed = time.monotonic() - start
            logger.error("generate_json timed out | model=%s latency=%.3fs", self._model, elapsed)
            raise RuntimeError(f"OpenAI request timed out for model={self._model}") from exc
        except APIConnectionError as exc:
            elapsed = time.monotonic() - start
            logger.error("generate_json connection failed | model=%s latency=%.3fs error=%s", self._model, elapsed, exc)
            raise RuntimeError(f"OpenAI connection failed for model={self._model}: {exc}") from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error("generate_json unexpected error | model=%s latency=%.3fs error=%s", self._model, elapsed, exc)
            raise RuntimeError(f"OpenAI request failed for model={self._model}: {exc}") from exc

        if response is None:
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
                raise RuntimeError(f"OpenAI request timed out for model={self._model}") from exc
            except APIConnectionError as exc:
                elapsed = time.monotonic() - start
                raise RuntimeError(f"OpenAI connection failed for model={self._model}: {exc}") from exc
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                elapsed = time.monotonic() - start
                raise RuntimeError(f"OpenAI request failed for model={self._model}: {exc}") from exc

        elapsed = time.monotonic() - start
        
        finish_reason: str | None = None
        try:
            finish_reason = response.choices[0].finish_reason
        except (AttributeError, IndexError):
            pass

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

        try:
            raw = response.choices[0].message.content
        except (AttributeError, IndexError, KeyError) as exc:
            raise RuntimeError(f"OpenAI returned an unexpected response structure for model={self._model}") from exc

        if raw is None:
            raise RuntimeError(f"OpenAI returned a None content field for model={self._model}.")

        if not raw.strip():
            raise RuntimeError(f"OpenAI returned an empty response for model={self._model}.")

        logger.debug("generate_json raw_preview | model=%s raw=%.300r", self._model, raw)

        cleaned = _strip_think_tags(raw)
        cleaned = _strip_fences(cleaned)
        cleaned = _extract_first_json(cleaned)

        logger.debug("generate_json cleaned_preview | model=%s cleaned=%.300r", self._model, cleaned)

        if not _is_json_complete(cleaned):
            raise RuntimeError(
                f"The model returned an incomplete JSON object after cleaning "
                f"(finish_reason={finish_reason!r}, model={self._model}, "
                f"max_tokens={max_tokens}). "
                f"Cleaned preview: {cleaned[:300]!r}"
            )

        return cleaned

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
                "stream completed | provider=openai model=%s latency=%.3fs",
                self._model, elapsed,
            )
        except (APIStatusError, APITimeoutError, APIConnectionError, Exception) as exc:
            elapsed = time.monotonic() - start
            logger.warning(
                "OpenAI streaming not available for model=%s (%.3fs): %s. "
                "Falling back to full generate().",
                self._model, elapsed, exc,
            )
            result = await self.generate(
                system_prompt, user_prompt,
                temperature=temperature, max_tokens=max_tokens,
            )
            yield result

    async def _chat_complete(
        self,
        messages: list[dict],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
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
            logger.error("OpenAI request timed out | model=%s latency=%.3fs", self._model, elapsed)
            raise RuntimeError(f"OpenAI request timed out for model={self._model}") from exc
        except APIConnectionError as exc:
            elapsed = time.monotonic() - start
            logger.error("OpenAI connection failed | model=%s latency=%.3fs error=%s", self._model, elapsed, exc)
            raise RuntimeError(f"OpenAI connection failed for model={self._model}: {exc}") from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error("OpenAI unexpected error | model=%s latency=%.3fs error=%s", self._model, elapsed, exc)
            raise RuntimeError(f"OpenAI request failed for model={self._model}: {exc}") from exc

        elapsed = time.monotonic() - start

        try:
            text = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
        except (AttributeError, IndexError, KeyError) as exc:
            raise RuntimeError(f"OpenAI returned an unexpected response structure for model={self._model}") from exc

        if text is None or not text.strip():
            raise RuntimeError(f"OpenAI returned an empty response for model={self._model}")

        usage = response.usage
        if usage:
            logger.info(
                "OpenAI completion | model=%s finish_reason=%s latency=%.3fs "
                "prompt_tokens=%d completion_tokens=%d total_tokens=%d",
                self._model, finish_reason, elapsed,
                usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
            )
        else:
            logger.info(
                "OpenAI completion | model=%s finish_reason=%s latency=%.3fs (no usage data)",
                self._model, finish_reason, elapsed,
            )

        return text.strip()

    def _normalize_status_error(
        self, exc: APIStatusError, elapsed: float
    ) -> RuntimeError:
        status_code: int = exc.status_code

        if status_code == 429:
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

            retry_after = headers.get("retry-after", "unknown")
            logger.error(
                "OpenAI 429 rate limit | model=%s latency=%.3fs retry_after=%s "
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
                f"OpenAI rate limit exceeded (429). "
                f"retry_after={retry_after}s. "
                f"remaining_tokens={headers.get('x-ratelimit-remaining-tokens', 'unknown')}. "
                f"Model: {self._model}."
            )

        message = _ERROR_MAP.get(
            status_code,
            f"OpenAI API error ({status_code}): {getattr(exc, 'message', str(exc))}",
        )
        logger.error(
            "OpenAI API error | model=%s status=%d latency=%.3fs message=%s",
            self._model, status_code, elapsed, message,
        )
        return RuntimeError(message)


def _build_messages(
    system_prompt: str,
    history: list[dict],
    user_prompt: str,
) -> list[dict]:
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
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<think>.*$", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        inner = lines[1:] if lines[0].startswith("```") else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        stripped = "\n".join(inner).strip()
    return stripped


def _extract_first_json(text: str) -> str:
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
