"""
Embedding generation for SmartTrip AI — centralized embedding service.

All embedding requests in the system (MemoryEngine, RetrievalEngine, and
any future engine) MUST go through embed_text() or embed_document() here.
No other module may call the Gemini embedding API directly.

Model: gemini-embedding-001
  - Replaces the retired text-embedding-004 model (deprecated by Google,
    returns HTTP 404 for any API version as of mid-2025).
  - Output dimensionality: fixed at 768 via EmbedContentConfig so all
    existing numpy vector indexes remain compatible without a full rebuild.
  - gemini-embedding-001 natively supports Matryoshka Representation
    Learning (MRL), meaning a 768-dim truncation retains strong quality.

Task types (important for RAG quality):
  - embed_query()    → task_type="RETRIEVAL_QUERY"    (user search strings)
  - embed_document() → task_type="RETRIEVAL_DOCUMENT" (indexed documents)
  - embed_text()     → task_type="RETRIEVAL_QUERY"    (backward-compatible alias)

Why text-embedding-004 failed:
  The google-genai SDK >=1.0 routes requests through the v1beta endpoint
  by default for non-GA models. text-embedding-004 was silently retired
  from that endpoint, producing HTTP 404 even with the correct model name
  string. gemini-embedding-001 is the current GA replacement.

Error handling:
  All functions raise RuntimeError with a complete diagnostic message on
  failure. No silent zero-vector fallback — callers must handle errors
  explicitly (the RetrievalEngine.retrieve() pipeline catches and re-raises
  with full context so the calling SCIF engine can decide the recovery path).
"""
from __future__ import annotations

import logging

from google.genai import errors, types

from app.core.config import get_settings
from app.core.gemini import client

logger = logging.getLogger(__name__)

settings = get_settings()

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------

# gemini-embedding-001: current GA embedding model, replaces text-embedding-004.
# Native output dim is 3072; we pin to 768 for backward compatibility with
# all existing vector indexes (which were built expecting 768-dim vectors).
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSION = 768          # pinned via output_dimensionality config


# ---------------------------------------------------------------------------
# Public embedding API
# ---------------------------------------------------------------------------

async def embed_query(text: str) -> list[float]:
    """
    Embed a user search query.

    Uses task_type=RETRIEVAL_QUERY so the model optimises the embedding
    for retrieval against a corpus — this is the correct task type for
    any string that will be compared against indexed documents.

    Returns a list of EMBEDDING_DIMENSION floats.
    Raises RuntimeError with a full diagnostic on any API failure.
    """
    return await _embed(text, task_type="RETRIEVAL_QUERY")


async def embed_document(text: str, *, title: str | None = None) -> list[float]:
    """
    Embed a document to be stored in a vector index.

    Uses task_type=RETRIEVAL_DOCUMENT. Optionally accepts a title which
    improves retrieval quality for longer structured documents.

    Returns a list of EMBEDDING_DIMENSION floats.
    Raises RuntimeError with a full diagnostic on any API failure.
    """
    config_kwargs: dict = {
        "task_type": "RETRIEVAL_DOCUMENT",
        "output_dimensionality": EMBEDDING_DIMENSION,
    }
    if title:
        config_kwargs["title"] = title

    return await _embed(text, **config_kwargs)


async def embed_text(text: str) -> list[float]:
    """
    Backward-compatible alias for embed_query().

    Kept so all existing callers (MemoryEngine, legacy code paths) continue
    to work without change.  New code should prefer embed_query() or
    embed_document() for semantically correct task types.
    """
    return await embed_query(text)


# ---------------------------------------------------------------------------
# Internal implementation
# ---------------------------------------------------------------------------

async def _embed(text: str, task_type: str = "RETRIEVAL_QUERY", **extra_config) -> list[float]:
    """
    Core embedding call.  All public functions delegate here.

    Raises RuntimeError — never returns a zero vector or swallows exceptions.
    """
    if not settings.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set — embedding unavailable"
        )

    if not text or not text.strip():
        raise RuntimeError("embed_text called with empty string — cannot embed empty content")

    # Truncate very long inputs to avoid exceeding the model's token limit
    # (gemini-embedding-001 supports up to ~2048 tokens; 8000 chars is safe)
    truncated = text[:8000]

    config = types.EmbedContentConfig(
        task_type=task_type,
        output_dimensionality=EMBEDDING_DIMENSION,
        **extra_config,
    )

    try:
        response = await client.aio.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=truncated,
            config=config,
        )
    except errors.APIError as exc:
        # Expose the full HTTP status code and message so logs are diagnostic
        raise RuntimeError(
            f"Gemini embedding API error "
            f"[model={EMBEDDING_MODEL}, task={task_type}, status={exc.code}]: "
            f"{exc.message}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"Unexpected error calling Gemini embedding API "
            f"[model={EMBEDDING_MODEL}, task={task_type}]: {exc!r}"
        ) from exc

    # Validate response shape
    if not response.embeddings:
        raise RuntimeError(
            f"Gemini returned an empty embeddings list "
            f"[model={EMBEDDING_MODEL}, text_len={len(truncated)}]"
        )

    values = list(response.embeddings[0].values)

    if len(values) != EMBEDDING_DIMENSION:
        raise RuntimeError(
            f"Gemini returned {len(values)}-dim vector but expected {EMBEDDING_DIMENSION} "
            f"[model={EMBEDDING_MODEL}]. The output_dimensionality config may have been "
            f"ignored — check SDK version compatibility."
        )

    logger.debug(
        "embed | model=%s | task=%s | input_len=%d | dim=%d",
        EMBEDDING_MODEL, task_type, len(truncated), len(values),
    )
    return values


# ---------------------------------------------------------------------------
# Cosine similarity utility (kept here for MemoryEngine backward compat)
# ---------------------------------------------------------------------------

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Brute-force cosine similarity.  For small per-user embedding counts
    (tens to low hundreds), an index adds maintenance cost without a
    measurable speed benefit — numpy vectorisation in VectorIndexManager
    handles the bulk search path.
    """
    if len(a) != len(b):
        raise ValueError(
            f"Embedding dimension mismatch: {len(a)} vs {len(b)}"
        )

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
