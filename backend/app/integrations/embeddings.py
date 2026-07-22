"""
Embedding generation via Gemini's embedding endpoint.

Kept as its own module (not folded into core/gemini.py) since it's a
distinct capability with a distinct model — text-embedding-004 rather than
a generative model — and Phase 3's design doc flags this as a swappable
decision (local sentence-transformers is the documented alternative if
embedding volume/cost becomes a concern later).
"""
from __future__ import annotations

from google.genai import errors

from app.core.config import get_settings
from app.core.gemini import client

settings = get_settings()

EMBEDDING_MODEL = "text-embedding-004"


async def embed_text(text: str) -> list[float]:
    """Returns a 768-dim embedding vector for the given text."""
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")

    try:
        response = await client.aio.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
        )
    except errors.APIError as exc:
        raise RuntimeError(f"Gemini embedding error ({exc.code}): {exc.message}") from exc

    if not response.embeddings:
        raise RuntimeError("Gemini returned no embedding for the given text")

    return list(response.embeddings[0].values)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Brute-force cosine similarity — deliberately not FAISS. Per-user
    long-term embedding counts are small (tens to low hundreds; see Phase 3
    design doc Section 9), so an index adds maintenance cost without a
    measurable speed benefit at this scale.
    """
    if len(a) != len(b):
        raise ValueError("Embedding dimension mismatch")

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
