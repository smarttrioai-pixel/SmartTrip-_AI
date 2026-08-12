"""
BaseLLMProvider — Abstract interface for all LLM providers in SmartTrip AI.

Every provider (HuggingFace, Gemini, future OpenAI, Anthropic, etc.) must
implement this interface. LLMService depends ONLY on BaseLLMProvider —
never on a concrete provider class. Switching providers requires changing
only the LLM_PROVIDER environment variable, with no code changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseLLMProvider(ABC):
    """
    Abstract base class for LLM text generation providers.

    All methods raise RuntimeError on failure with a meaningful message.
    Concrete providers must NOT raise provider-specific exceptions — they
    must normalize all SDK/HTTP errors to RuntimeError before returning,
    so LLMService (and the FastAPI routes above it) never import or catch
    provider-specific error types.
    """

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """
        Generate a plain text response.

        Args:
            system_prompt: Instruction context for the model.
            user_prompt:   The user-facing prompt / query.
            temperature:   Sampling temperature (0.0 = deterministic).
            max_tokens:    Maximum tokens in the response.

        Returns:
            Generated text string.

        Raises:
            RuntimeError: On any provider error (normalized from SDK errors).
        """

    @abstractmethod
    async def chat(
        self,
        system_prompt: str,
        history: list[dict],
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """
        Multi-turn conversational completion.

        Args:
            system_prompt: System instruction for the assistant.
            history:       List of prior turns: [{"role": "user"|"assistant", "content": "..."}]
            user_prompt:   The current user message.
            temperature:   Sampling temperature.
            max_tokens:    Maximum tokens in the response.

        Returns:
            Assistant reply string.

        Raises:
            RuntimeError: On any provider error.
        """

    @abstractmethod
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

        The provider must instruct the model to return JSON only and
        return the raw text. Validation, parsing, and retry logic are
        the responsibility of LLMService.generate_json(), not the provider.

        Args:
            system_prompt: Instruction context (will be augmented to require JSON output).
            user_prompt:   The user-facing prompt.
            temperature:   Lower temperature for more deterministic JSON.
            max_tokens:    Maximum tokens in the response.

        Returns:
            Raw response string (expected to be valid JSON).

        Raises:
            RuntimeError: On any provider error.
        """

    @abstractmethod
    async def summarize(
        self,
        text: str,
        *,
        max_tokens: int = 512,
    ) -> str:
        """
        Summarize the given text.

        Args:
            text:       The text to summarize.
            max_tokens: Maximum tokens for the summary.

        Returns:
            Summary string.

        Raises:
            RuntimeError: On any provider error.
        """

    @abstractmethod
    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """
        Stream a generated response as an async iterator of text chunks.

        Providers that do not support streaming should yield the full
        `generate()` result as a single chunk — this keeps the interface
        consistent and lets LLMService.stream() work regardless of provider.

        Args:
            system_prompt: Instruction context.
            user_prompt:   The user-facing prompt.
            temperature:   Sampling temperature.
            max_tokens:    Maximum tokens in the response.

        Yields:
            String chunks as they arrive from the provider.

        Raises:
            RuntimeError: On any provider error.
        """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier used in logs (e.g. 'huggingface', 'gemini')."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The model identifier currently in use (e.g. 'google/gemma-3-4b-it')."""
