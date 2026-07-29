"""
Multi-Factor Ranker for SmartTrip AI Retrieval Engine (SCIF Phase 5).

Ranks and deduplicates a merged list of RetrievedDocument objects from
parallel index searches into a final, ordered, non-redundant result set.

Ranking formula (weights sum to 1.0):
  composite = (
      0.45 * similarity_score      # cosine similarity — primary signal
    + 0.20 * recency_score         # exponential decay (half-life 30 days)
    + 0.20 * importance_score      # document weight / explicit importance tag
    + 0.15 * user_relevance_score  # interest keyword overlap
  )

Deduplication:
  Near-duplicate documents (identical content hash OR both similarity ≥ 0.95
  AND content hash prefix matches) are suppressed — only the highest-ranked
  copy is retained.  This prevents the same preference or POI from flooding
  the context window.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Sequence

from app.engines.retrieval_models import IndexType, RetrievedDocument

logger = logging.getLogger(__name__)

# Composite score weights — must sum to 1.0
_W_SIMILARITY = 0.45
_W_RECENCY = 0.20
_W_IMPORTANCE = 0.20
_W_USER_RELEVANCE = 0.15

assert abs(_W_SIMILARITY + _W_RECENCY + _W_IMPORTANCE + _W_USER_RELEVANCE - 1.0) < 1e-9

# Deduplication threshold: suppress a document if a higher-ranked document
# already in the result set has the same 8-char content hash prefix.
_DEDUP_HASH_PREFIX_LEN = 8


def _content_hash_prefix(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:_DEDUP_HASH_PREFIX_LEN]


class Ranker:
    """
    Stateless ranker — one instance can be safely shared across requests.
    """

    def rank_and_deduplicate(
        self,
        documents: Sequence[RetrievedDocument],
        *,
        top_k: int = 8,
    ) -> list[RetrievedDocument]:
        """
        1. Compute composite score for every document.
        2. Sort descending by composite score.
        3. Remove near-duplicates (keep highest-ranked copy).
        4. Return top_k.
        """
        if not documents:
            return []

        # Step 1 — score
        scored: list[RetrievedDocument] = []
        for doc in documents:
            composite = (
                _W_SIMILARITY * doc.similarity_score
                + _W_RECENCY * doc.recency_score
                + _W_IMPORTANCE * doc.importance_score
                + _W_USER_RELEVANCE * doc.user_relevance_score
            )
            # Pydantic model is not frozen so we can mutate in place
            doc.composite_score = round(composite, 4)
            scored.append(doc)

        # Step 2 — sort
        scored.sort(key=lambda d: d.composite_score, reverse=True)

        # Step 3 — deduplicate
        seen_hashes: set[str] = set()
        unique: list[RetrievedDocument] = []
        for doc in scored:
            h = _content_hash_prefix(doc.content)
            if h in seen_hashes:
                logger.debug("Ranker: suppressed near-duplicate content hash=%s", h)
                continue
            seen_hashes.add(h)
            unique.append(doc)

        result = unique[:top_k]

        logger.debug(
            "Ranker | input=%d | after_dedup=%d | returned=%d | top_score=%.4f",
            len(documents),
            len(unique),
            len(result),
            result[0].composite_score if result else 0.0,
        )
        return result

    def compute_confidence(self, documents: list[RetrievedDocument]) -> float:
        """
        Returns the mean composite score of the returned document set as a
        proxy for retrieval confidence.  Returns 0.0 for an empty set.
        """
        if not documents:
            return 0.0
        return round(sum(d.composite_score for d in documents) / len(documents), 4)

    def per_index_confidence(
        self, documents: list[RetrievedDocument]
    ) -> dict[IndexType, float]:
        """
        Break down mean composite score per index type.  Useful for the
        StructuredContext confidence fields.
        """
        buckets: dict[IndexType, list[float]] = {it: [] for it in IndexType}
        for doc in documents:
            buckets[doc.index_type].append(doc.composite_score)
        return {
            it: (round(sum(scores) / len(scores), 4) if scores else 0.0)
            for it, scores in buckets.items()
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_ranker: Ranker | None = None


def get_ranker() -> Ranker:
    global _ranker
    if _ranker is None:
        _ranker = Ranker()
    return _ranker
