"""
Vector Indexes for SmartTrip AI Retrieval Engine (SCIF Phase 5).

Three independent, named vector indexes, each scoped to a specific domain
of knowledge.  All share the same underlying numpy cosine-similarity
implementation (identical to the existing FAISSVectorStore pattern) but are
kept strictly isolated so they can be searched independently and migrated
to different backends (FAISS, Qdrant, Pinecone, Milvus) without touching
the engine's public interface.

Indexes:
  MemoryVectorIndex       — user preferences, behavioral data, chat memories,
                            diary entries, personal profile facts.
  DestinationVectorIndex  — tourist attractions, hotels, restaurants, museums,
                            landmarks fed from OpenTripMap results.
  ResearchVectorIndex     — tourism papers, local regulations, historical
                            documents (starts empty; populated via ingestion).

VectorIndexManager        — owns all three, exposes parallel async search.
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Any

import numpy as np

from app.engines.retrieval_models import IndexType, RetrievedDocument
from app.integrations.embeddings import EMBEDDING_DIMENSION

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Low-level numpy cosine similarity (vectorised for speed)
# ---------------------------------------------------------------------------

def _cosine_similarity_batch(query: list[float], corpus: np.ndarray) -> np.ndarray:
    """
    Compute cosine similarity between one query vector and every row in
    corpus (shape: [N, D]) using numpy vectorisation.

    Falls back gracefully when corpus is empty.
    """
    if corpus.shape[0] == 0:
        return np.array([], dtype=np.float32)

    q = np.array(query, dtype=np.float32)
    q_norm = np.linalg.norm(q)
    if q_norm == 0:
        return np.zeros(corpus.shape[0], dtype=np.float32)

    q_unit = q / q_norm
    c_norms = np.linalg.norm(corpus, axis=1, keepdims=True)
    # Avoid division-by-zero for zero vectors
    c_norms = np.where(c_norms == 0, 1.0, c_norms)
    c_unit = corpus / c_norms
    return (c_unit @ q_unit).astype(np.float32)


# ---------------------------------------------------------------------------
# Base vector index
# ---------------------------------------------------------------------------

class _BaseVectorIndex:
    """
    Abstract base class for a named vector index.

    Internal storage:
      _vectors  : np.ndarray  shape [N, D], float32
      _metadata : list[dict]  parallel to rows in _vectors

    The dimension defaults to EMBEDDING_DIMENSION (from embeddings.py) so
    any change to the embedding model's output size is automatically
    reflected here without touching this file.
    """

    index_type: IndexType  # must be set by subclass

    def __init__(self, dimension: int = EMBEDDING_DIMENSION) -> None:
        self._dimension = dimension
        self._vectors: np.ndarray = np.empty((0, dimension), dtype=np.float32)
        self._metadata: list[dict[str, Any]] = []
        logger.debug("Initialised %s (dim=%d)", self.__class__.__name__, dimension)

    # ------------------------------------------------------------------
    # Write methods
    # ------------------------------------------------------------------

    def add(
        self,
        *,
        text: str,
        vector: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a single document to the index."""
        if len(vector) != self._dimension:
            raise ValueError(
                f"{self.__class__.__name__}: vector dim {len(vector)} "
                f"!= index dim {self._dimension}"
            )
        row = np.array(vector, dtype=np.float32).reshape(1, -1)
        self._vectors = np.vstack([self._vectors, row]) if self._vectors.shape[0] > 0 else row
        self._metadata.append({
            "content": text,
            "source_type": metadata.get("source_type", "unknown") if metadata else "unknown",
            "timestamp": metadata.get("timestamp", datetime.now(timezone.utc)) if metadata else datetime.now(timezone.utc),
            "importance": metadata.get("importance", 1.0) if metadata else 1.0,
            **(metadata or {}),
        })

    def add_batch(self, items: list[dict[str, Any]]) -> None:
        """
        Bulk-add items.  Each item must have keys: text, vector, metadata (opt).
        """
        for item in items:
            self.add(
                text=item["text"],
                vector=item["vector"],
                metadata=item.get("metadata"),
            )

    def clear(self) -> None:
        """Reset the index."""
        self._vectors = np.empty((0, self._dimension), dtype=np.float32)
        self._metadata.clear()

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        return self._vectors.shape[0]

    def search(
        self,
        query_vector: list[float],
        *,
        top_k: int = 8,
        min_score: float = 0.45,
        user_interests: list[str] | None = None,
    ) -> list[RetrievedDocument]:
        """
        Return up to top_k documents sorted by cosine similarity to query_vector.
        Documents with score < min_score are excluded.
        """
        if self.size == 0:
            return []

        scores = _cosine_similarity_batch(query_vector, self._vectors)
        now = datetime.now(timezone.utc)
        results: list[RetrievedDocument] = []

        for idx, score in enumerate(scores):
            if float(score) < min_score:
                continue
            meta = self._metadata[idx]
            doc = self._build_document(
                meta=meta,
                similarity_score=float(score),
                now=now,
                user_interests=user_interests or [],
            )
            results.append(doc)

        results.sort(key=lambda d: d.similarity_score, reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_document(
        self,
        meta: dict[str, Any],
        similarity_score: float,
        now: datetime,
        user_interests: list[str],
    ) -> RetrievedDocument:
        """Build a RetrievedDocument from raw metadata + scores."""
        timestamp = meta.get("timestamp", now)
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except ValueError:
                timestamp = now

        recency = self._recency_score(timestamp, now)
        importance = float(meta.get("importance", 1.0))
        importance = max(0.0, min(1.0, importance))

        content = meta.get("content", "")
        user_rel = self._user_relevance(content, user_interests)

        return RetrievedDocument(
            content=content,
            source_type=meta.get("source_type", "unknown"),
            index_type=self.index_type,
            similarity_score=round(similarity_score, 4),
            recency_score=round(recency, 4),
            importance_score=round(importance, 4),
            user_relevance_score=round(user_rel, 4),
            source_metadata={k: v for k, v in meta.items() if k not in ("content", "vector")},
            timestamp=timestamp if isinstance(timestamp, datetime) else now,
        )

    @staticmethod
    def _recency_score(timestamp: datetime, now: datetime) -> float:
        """Exponential decay with 30-day half-life."""
        try:
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            age_days = (now - timestamp).total_seconds() / 86_400
            return math.exp(-0.693 * age_days / 30.0)  # half-life = 30 days
        except Exception:
            return 0.5

    @staticmethod
    def _user_relevance(content: str, interests: list[str]) -> float:
        """Keyword overlap between document text and user's declared interests."""
        if not interests:
            return 0.5
        lower = content.lower()
        matches = sum(1 for i in interests if i.lower() in lower)
        if matches == 0:
            return 0.3
        return min(1.0, 0.5 + 0.2 * matches)


# ---------------------------------------------------------------------------
# Three named indexes
# ---------------------------------------------------------------------------

class MemoryVectorIndex(_BaseVectorIndex):
    """
    Index for user-specific memory: long-term preferences, inferred
    preferences, behavioral summaries, chat memories, diary entries,
    personal profile facts.

    Document source_type values:
      'preference'      — LongTermMemory.embeddings
      'inferred_pref'   — LongTermMemory.inferred_preferences
      'behavioral'      — BehavioralMemory summary snippets
      'chat_memory'     — ChatMessage summaries
      'diary_entry'     — Diary entries
      'profile'         — User profile facts
      'trip_history'    — Saved trip summaries
    """
    index_type = IndexType.MEMORY


class DestinationVectorIndex(_BaseVectorIndex):
    """
    Index for place/destination data: POIs from OpenTripMap, hotels,
    restaurants, museums, landmarks, itinerary activities scored by
    RecommendationEngine.

    Document source_type values:
      'poi'             — OpenTripMap POI
      'activity'        — Gemini-generated itinerary activity
      'hotel'           — Hotel result
      'restaurant'      — Restaurant result
      'landmark'        — Wikipedia landmark
    """
    index_type = IndexType.DESTINATION


class ResearchVectorIndex(_BaseVectorIndex):
    """
    Index for structured knowledge: IEEE papers, tourism research,
    sustainable tourism guidelines, local regulations, historical docs.
    Starts empty; populated via a future document-ingestion pipeline.

    Document source_type values:
      'research_paper'  — Embedded academic paper chunk
      'tourism_guide'   — Tourism knowledge base chunk
      'regulation'      — Local law / regulation
      'historical'      — Historical document
    """
    index_type = IndexType.RESEARCH


# ---------------------------------------------------------------------------
# Index manager — parallel search coordinator
# ---------------------------------------------------------------------------

class VectorIndexManager:
    """
    Owns all three named indexes and provides a single interface for
    parallel async search across any combination of them.

    Thread safety: the underlying numpy operations are GIL-held; asyncio
    concurrency via `asyncio.gather` is safe here because searches are
    CPU-bound pure-Python / numpy — they complete without yielding, which
    is fine given the small per-user corpus sizes (< few hundred docs per
    index at current scale).  When migrating to FAISS/Qdrant, swap the
    sync search call inside `_search_one` for an async client call.
    """

    def __init__(self, dimension: int = EMBEDDING_DIMENSION) -> None:
        self.memory = MemoryVectorIndex(dimension)
        self.destination = DestinationVectorIndex(dimension)
        self.research = ResearchVectorIndex(dimension)

        self._index_map: dict[IndexType, _BaseVectorIndex] = {
            IndexType.MEMORY: self.memory,
            IndexType.DESTINATION: self.destination,
            IndexType.RESEARCH: self.research,
        }

    def get(self, index_type: IndexType) -> _BaseVectorIndex:
        return self._index_map[index_type]

    async def search_parallel(
        self,
        query_vector: list[float],
        index_types: list[IndexType],
        *,
        top_k: int = 8,
        min_score: float = 0.45,
        user_interests: list[str] | None = None,
    ) -> list[RetrievedDocument]:
        """
        Search the requested indexes in parallel via asyncio.gather and
        return a merged, unsorted list of all candidates.
        Sorting / deduplication is handled by the Ranker.
        """
        tasks = [
            asyncio.to_thread(
                self._index_map[idx].search,
                query_vector,
                top_k=top_k,
                min_score=min_score,
                user_interests=user_interests,
            )
            for idx in index_types
            if idx in self._index_map
        ]

        if not tasks:
            return []

        results_per_index: list[list[RetrievedDocument]] = await asyncio.gather(*tasks)
        merged: list[RetrievedDocument] = []
        for docs in results_per_index:
            merged.extend(docs)

        logger.debug(
            "VectorIndexManager.search_parallel | indexes=%s | candidates=%d",
            [i.value for i in index_types],
            len(merged),
        )
        return merged

    def stats(self) -> dict[str, int]:
        return {
            IndexType.MEMORY.value: self.memory.size,
            IndexType.DESTINATION.value: self.destination.size,
            IndexType.RESEARCH.value: self.research.size,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: VectorIndexManager | None = None


def get_vector_index_manager() -> VectorIndexManager:
    """
    Returns the process-level singleton VectorIndexManager.
    Indexes persist for the lifetime of the process — they are populated
    from Firestore / OpenTripMap data as requests flow through.

    The dimension is derived from EMBEDDING_DIMENSION in embeddings.py so
    it stays in sync with the embedding model's output size automatically.
    """
    global _manager
    if _manager is None:
        _manager = VectorIndexManager(dimension=EMBEDDING_DIMENSION)
    return _manager
