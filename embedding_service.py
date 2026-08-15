"""
EmbeddingService for SmartTrip AI.

A dedicated, provider-independent service for text embedding generation.
Embeddings are intentionally kept separate from LLMService — they are a
distinct AI capability (vector representation, not text generation), use
a different model type, and have different latency/caching characteristics.

Current implementation:
  - Primary: Hugging Face Inference API (feature_extraction endpoint)
    via huggingface_hub.AsyncInferenceClient with a sentence-transformers model.
  - The module docstring in embeddings.py itself identified
    sentence-transformers as the documented alternative. This implements it.

Future-proof:
  - A provider abstraction can be added here (BaseEmbeddingProvider) if
    a second embedding provider is needed.
  - Batch embedding (embed_batch) is implemented natively.
  - An in-process LRU cache avoids re-embedding the same string within a
    request or across repeated calls for stable strings (e.g. preference text).

Consumers:
  - MemoryEngine (preference similarity search)
  - All callers of the existing embed_text() in integrations/embeddings.py
    continue to work — that module is updated to delegate here.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

# Maximum number of (text → vector) pairs held in the in-process cache.
# Embeddings are deterministic for a given model+text, so caching is safe.
_CACHE_MAX = 512

# Simple bounded cache: {hash(text) → vector}
_embedding_cache: dict[str, list[float]] = {}


class EmbeddingService:
    """
    Service for generating text embedding vectors.

    Initialized with a HuggingFace AsyncInferenceClient (or any object with
    a compatible `feature_extraction(text, model)` async method) and a model
    name. The client and model are injected — no global state, no singletons,
    fully testable.
    """

    def __init__(self, client: Any, model: str) -> None:
        """
        Args:
            client: An `huggingface_hub.AsyncInferenceClient` instance.
            model:  The sentence-transformers model to use for embeddings.
                    Example: "sentence-transformers/all-MiniLM-L6-v2"
        """
        self._client = client
        self._model = model
        logger.info("EmbeddingService initialized with model=%s", model)

    async def embed_text(self, text: str) -> list[float]:
        """
        Return a normalized embedding vector for the given text.

        Results are cached in process by a content hash — identical inputs
        always return the same vector without a network round-trip.

        Args:
            text: The text to embed.

        Returns:
            List of floats (embedding vector). Dimension depends on model
            (all-MiniLM-L6-v2 → 384-dim).

        Raises:
            RuntimeError: On network failure, auth failure, or unexpected
                          response shape.
        """
        if not text or not text.strip():
            raise RuntimeError("Cannot embed empty text.")

        cache_key = _cache_key(text, self._model)
        if cache_key in _embedding_cache:
            return _embedding_cache[cache_key]

        start = time.monotonic()
        try:
            response = await self._client.feature_extraction(
                text=text.strip(),
                model=self._model,
            )
        except Exception as exc:
            raise RuntimeError(
                f"EmbeddingService failed to embed text with model={self._model}: {exc}"
            ) from exc

        vector = _extract_vector(response)
        elapsed = time.monotonic() - start
        logger.debug(
            "embed_text | model=%s latency=%.3fs dim=%d cached=%d",
            self._model, elapsed, len(vector), len(_embedding_cache),
        )

        # Evict oldest entry if cache is full
        if len(_embedding_cache) >= _CACHE_MAX:
            oldest_key = next(iter(_embedding_cache))
            del _embedding_cache[oldest_key]

        _embedding_cache[cache_key] = vector
        return vector

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embed multiple texts concurrently.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors in the same order as `texts`.

        Raises:
            RuntimeError: If any individual embedding fails.
        """
        if not texts:
            return []

        tasks = [self.embed_text(t) for t in texts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        vectors: list[list[float]] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                raise RuntimeError(
                    f"embed_batch failed on item {i}: {result}"
                ) from result
            vectors.append(result)

        return vectors


# ------------------------------------------------------------------
# Module-level cosine similarity (shared, no external deps)
# ------------------------------------------------------------------

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Compute cosine similarity between two embedding vectors.

    Kept as a module-level function (not a method) so MemoryEngine and
    other consumers can import just this without constructing a service.

    Args:
        a: First embedding vector.
        b: Second embedding vector.

    Returns:
        Similarity score in [-1, 1]. Returns 0.0 for zero-length vectors.

    Raises:
        ValueError: If vectors have different dimensions.
    """
    if len(a) != len(b):
        raise ValueError(
            f"Embedding dimension mismatch: {len(a)} vs {len(b)}"
        )
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _cache_key(text: str, model: str) -> str:
    """Deterministic cache key for (text, model) pairs."""
    digest = hashlib.sha256(f"{model}||{text}".encode()).hexdigest()[:32]
    return digest


def _extract_vector(response: Any) -> list[float]:
    """
    Normalize the HF feature_extraction response to a flat float list.

    The response shape from HF feature_extraction varies:
      - Sentence-transformers models: list of floats (single vector) or
        list of list of floats (one per token → mean-pool needed).
      - The client may return numpy arrays or plain lists.

    We normalize to a plain Python list[float] in all cases.
    """
    # Convert numpy arrays if present (huggingface_hub may return them)
    try:
        import numpy as np
        if isinstance(response, np.ndarray):
            if response.ndim == 2:
                # Token-level embeddings — mean pool to get sentence vector
                response = response.mean(axis=0)
            return response.tolist()
    except ImportError:
        pass

    if isinstance(response, list):
        if response and isinstance(response[0], list):
            # list of lists (token-level) — mean pool
            n = len(response)
            dim = len(response[0])
            pooled = [sum(response[i][j] for i in range(n)) / n for j in range(dim)]
            return pooled
        # Already a flat list of floats
        return [float(x) for x in response]

    raise RuntimeError(
        f"Unexpected embedding response type from HuggingFace: {type(response)}"
    )
