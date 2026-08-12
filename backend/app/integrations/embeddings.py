"""
Embedding generation for SmartTrip AI.

IMPORTANT: This module is the backward-compatible shim layer for
MemoryEngine and other callers that use `from app.integrations.embeddings
import embed_text, cosine_similarity`. The actual implementation now lives
in app/services/embedding_service.py (EmbeddingService + EmbeddingService.
cosine_similarity).

This module bootstraps a shared EmbeddingService instance from config
(HF_API_TOKEN + HF_EMBEDDING_MODEL) and exposes the same function
signatures as before so that existing callers in MemoryEngine etc.
continue to work without any changes.

Previously: Used Gemini's text-embedding-004 endpoint.
Now:        Uses HuggingFace feature_extraction with sentence-transformers.

The module docstring in the previous version explicitly stated:
  "local sentence-transformers is the documented alternative if embedding
   volume/cost becomes a concern later."
This implements that documented plan.

DO NOT call Gemini from this module. All embedding calls go through
EmbeddingService → HuggingFace Inference API.
"""
from __future__ import annotations

import logging

from app.core.config import get_settings
from app.services.embedding_service import (
    EmbeddingService,
    cosine_similarity as _cosine_similarity,
)

logger = logging.getLogger(__name__)

settings = get_settings()

# ---------------------------------------------------------------------------
# Shared EmbeddingService instance (module-level singleton).
# Initialized lazily on first use so a missing HF_API_TOKEN doesn't crash
# the app at import time \u2014 only the endpoints that need embeddings will fail.
# ---------------------------------------------------------------------------
_embedding_service: EmbeddingService | None = None


def _get_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        from huggingface_hub import AsyncInferenceClient

        if not settings.HF_API_TOKEN:
            raise RuntimeError(
                "HF_API_TOKEN is required for embedding generation. "
                "Set HF_API_TOKEN in your environment or .env file."
            )
        client = AsyncInferenceClient(token=settings.HF_API_TOKEN)
        _embedding_service = EmbeddingService(
            client=client,
            model=settings.HF_EMBEDDING_MODEL,
        )
    return _embedding_service


async def embed_text(text: str) -> list[float]:
    """
    Return a normalized embedding vector for the given text.

    Backward-compatible entry point used by MemoryEngine and other callers.
    Delegates to EmbeddingService (HuggingFace feature_extraction).

    Args:
        text: Text to embed.

    Returns:
        List of floats (embedding vector).

    Raises:
        RuntimeError: On network failure, auth failure, or unexpected response.
    """
    return await _get_service().embed_text(text)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Compute cosine similarity between two embedding vectors.

    Backward-compatible entry point. Delegates to the shared implementation
    in app.services.embedding_service.

    Args:
        a: First embedding vector.
        b: Second embedding vector.

    Returns:
        Similarity score in [-1, 1].
    """
    return _cosine_similarity(a, b)
