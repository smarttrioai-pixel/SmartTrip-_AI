"""
Retrieval Models — typed Pydantic v2 and dataclass definitions for the
entire SmartTrip AI Retrieval Engine layer (SCIF Phase 5).

Design rules:
- Every public method in retrieval_engine.py accepts / returns types from here.
- No `dict` leakage in function signatures that cross module boundaries.
- Pydantic models are used for external-facing structures (so they're
  JSON-serializable for logging / future API exposure).
- Dataclasses are used for internal computation structures to avoid
  Pydantic validation overhead in the hot retrieval path.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class IndexType(str, Enum):
    """The three independent vector indexes in the retrieval layer."""
    MEMORY = "memory"
    DESTINATION = "destination"
    RESEARCH = "research"


class QueryIntent(str, Enum):
    """
    Classified intent of an incoming query.  The RetrievalRouter maps each
    intent to one or more IndexType values to search.
    """
    TRAVEL_PLANNING = "travel_planning"
    USER_PERSONALIZATION = "user_personalization"
    ACADEMIC_RESEARCH = "academic_research"
    CHAT = "chat"
    GENERAL_RECOMMENDATION = "general_recommendation"


# ---------------------------------------------------------------------------
# Core retrieval document
# ---------------------------------------------------------------------------

class RetrievedDocument(BaseModel):
    """
    A single document returned from a vector index search, enriched with
    all the signals the Ranker needs to compute a final weighted score.
    """
    # Content
    content: str = Field(description="The raw text that was indexed")
    source_type: str = Field(description="E.g. 'preference', 'trip_history', 'poi', 'research'")
    index_type: IndexType = Field(description="Which index this document came from")

    # Scoring signals (all in [0, 1])
    similarity_score: float = Field(ge=0.0, le=1.0, description="Cosine similarity to query")
    recency_score: float = Field(default=1.0, ge=0.0, le=1.0)
    importance_score: float = Field(default=1.0, ge=0.0, le=1.0)
    user_relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)

    # Final composite score (computed by Ranker)
    composite_score: float = Field(default=0.0, ge=0.0, le=1.0)

    # Provenance / metadata
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    document_id: str = Field(default="")

    def compute_document_id(self) -> "RetrievedDocument":
        """Stable ID based on content hash — used for deduplication."""
        h = hashlib.sha256(self.content.encode()).hexdigest()[:16]
        object.__setattr__(self, "document_id", h)
        return self

    model_config = {"frozen": False}


# ---------------------------------------------------------------------------
# Retrieval result
# ---------------------------------------------------------------------------

class RetrievalResult(BaseModel):
    """
    The fully ranked and deduplicated output of one retrieval operation.
    This is what every public method on RetrievalEngine returns.
    """
    documents: list[RetrievedDocument] = Field(default_factory=list)
    query: str = ""
    indexes_searched: list[IndexType] = Field(default_factory=list)
    intent: QueryIntent = QueryIntent.CHAT
    total_candidates: int = 0        # documents before deduplication
    returned_count: int = 0          # documents after dedup + top-k cut
    confidence: float = 0.0          # avg composite score of returned docs
    execution_time_ms: float = 0.0
    cache_hit: bool = False


# ---------------------------------------------------------------------------
# Structured context (output to Gemini)
# ---------------------------------------------------------------------------

class StructuredContext(BaseModel):
    """
    Human-readable, structured context assembled from retrieval results,
    ready to be injected into any Gemini prompt.

    This is the drop-in replacement for the old MemoryContext — it exposes
    `as_prompt_text()` with the same signature as the old
    `MemoryContext.as_prompt_context()`.
    """
    # Per-index buckets (human-readable text blocks)
    memory_context: str = ""
    destination_context: str = ""
    research_context: str = ""

    # Confidence per index bucket
    memory_confidence: float = 0.0
    destination_confidence: float = 0.0
    research_confidence: float = 0.0

    # Raw documents (available for downstream engines if they want fine-grained access)
    memory_documents: list[RetrievedDocument] = Field(default_factory=list)
    destination_documents: list[RetrievedDocument] = Field(default_factory=list)
    research_documents: list[RetrievedDocument] = Field(default_factory=list)

    # Source metadata for explainability
    source_metadata: list[dict[str, Any]] = Field(default_factory=list)

    # Retrieval provenance
    query: str = ""
    intent: QueryIntent = QueryIntent.CHAT
    indexes_searched: list[IndexType] = Field(default_factory=list)
    total_documents_retrieved: int = 0
    execution_time_ms: float = 0.0
    cache_hit: bool = False

    def as_prompt_text(self) -> str:
        """
        Returns a structured text block ready for Gemini prompt injection.
        Mirrors the old MemoryContext.as_prompt_context() signature so
        callers can do a one-line swap.
        """
        parts: list[str] = []

        if self.memory_context:
            parts.append(f"[Relevant User Memory]\n{self.memory_context}")

        if self.destination_context:
            parts.append(f"[Relevant Places & Destinations]\n{self.destination_context}")

        if self.research_context:
            parts.append(f"[Relevant Research & Knowledge]\n{self.research_context}")

        if not parts:
            return ""

        header = (
            f"[SmartTrip AI Cognitive Context | "
            f"Intent: {self.intent.value} | "
            f"Sources: {', '.join(i.value for i in self.indexes_searched)} | "
            f"Confidence: {self.memory_confidence:.0%}]"
        )
        return header + "\n\n" + "\n\n".join(parts)

    def is_empty(self) -> bool:
        return not (self.memory_context or self.destination_context or self.research_context)


# ---------------------------------------------------------------------------
# Retrieval request
# ---------------------------------------------------------------------------

class RetrievalRequest(BaseModel):
    """
    Typed input to RetrievalEngine.retrieve().
    Covers every retrieval use-case via optional fields.
    """
    query: str = Field(description="The raw user query or context string to embed and search")
    user_id: str | None = None
    chat_id: str | None = None

    # Override auto-routing if you know exactly what you want
    index_types: list[IndexType] | None = Field(
        default=None,
        description="Explicit index override — if None, RetrievalRouter decides automatically",
    )
    forced_intent: QueryIntent | None = None

    # Search parameters
    top_k: int = Field(default=8, ge=1, le=50)
    min_similarity: float = Field(default=0.45, ge=0.0, le=1.0)

    # Context hints for relevance scoring
    user_interests: list[str] = Field(default_factory=list)

    # Cache control
    bypass_cache: bool = False


# ---------------------------------------------------------------------------
# Cache statistics
# ---------------------------------------------------------------------------

@dataclass
class CacheStats:
    embedding_hits: int = 0
    embedding_misses: int = 0
    search_hits: int = 0
    search_misses: int = 0

    @property
    def embedding_hit_rate(self) -> float:
        total = self.embedding_hits + self.embedding_misses
        return self.embedding_hits / total if total > 0 else 0.0

    @property
    def search_hit_rate(self) -> float:
        total = self.search_hits + self.search_misses
        return self.search_hits / total if total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "embedding_hits": self.embedding_hits,
            "embedding_misses": self.embedding_misses,
            "embedding_hit_rate": round(self.embedding_hit_rate, 3),
            "search_hits": self.search_hits,
            "search_misses": self.search_misses,
            "search_hit_rate": round(self.search_hit_rate, 3),
        }
