"""
Context Builder for SmartTrip AI Retrieval Engine (SCIF Phase 5).

Takes a ranked list of RetrievedDocument objects and assembles a
StructuredContext that:
  1. Groups documents by IndexType (memory / destination / research).
  2. Formats each group as a human-readable prose block for Gemini.
  3. Computes per-group and overall confidence scores.
  4. Provides `as_prompt_text()` — a drop-in replacement for the old
     MemoryContext.as_prompt_context() method.

The formatting is deliberately verbose and structured so that Gemini can
distinguish the source and reliability of each piece of context rather than
treating everything as an undifferentiated wall of text.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Sequence

from app.engines.ranking import Ranker
from app.engines.retrieval_models import (
    IndexType,
    QueryIntent,
    RetrievedDocument,
    StructuredContext,
)

logger = logging.getLogger(__name__)

# Maximum characters per context block before it is truncated.
# Protects against excessively long Gemini prompts.
_MAX_BLOCK_CHARS = 3_000
_MAX_DOCS_PER_BLOCK = 6


class ContextBuilder:
    """
    Assembles a StructuredContext from a list of ranked documents.

    Usage:
        builder = ContextBuilder(ranker)
        ctx = builder.build(
            documents=ranked_docs,
            query="plan a trip to Kyoto",
            intent=QueryIntent.TRAVEL_PLANNING,
            indexes_searched=[IndexType.DESTINATION],
            execution_time_ms=42.3,
            cache_hit=False,
        )
        prompt_text = ctx.as_prompt_text()
    """

    def __init__(self, ranker: Ranker) -> None:
        self._ranker = ranker

    def build(
        self,
        documents: list[RetrievedDocument],
        *,
        query: str,
        intent: QueryIntent,
        indexes_searched: list[IndexType],
        execution_time_ms: float,
        cache_hit: bool,
    ) -> StructuredContext:
        """Build and return a StructuredContext from ranked documents."""

        # Split by index
        memory_docs = [d for d in documents if d.index_type == IndexType.MEMORY]
        dest_docs = [d for d in documents if d.index_type == IndexType.DESTINATION]
        research_docs = [d for d in documents if d.index_type == IndexType.RESEARCH]

        # Compute per-index confidence
        per_index_conf = self._ranker.per_index_confidence(documents)

        # Format text blocks
        memory_text = self._format_memory_block(memory_docs)
        dest_text = self._format_destination_block(dest_docs)
        research_text = self._format_research_block(research_docs)

        # Aggregate source metadata for explainability
        source_meta = [
            {
                "content_preview": d.content[:80],
                "source_type": d.source_type,
                "index": d.index_type.value,
                "similarity": d.similarity_score,
                "composite": d.composite_score,
                "timestamp": d.timestamp.isoformat() if d.timestamp else None,
            }
            for d in documents
        ]

        ctx = StructuredContext(
            # Text blocks
            memory_context=memory_text,
            destination_context=dest_text,
            research_context=research_text,
            # Confidence
            memory_confidence=per_index_conf.get(IndexType.MEMORY, 0.0),
            destination_confidence=per_index_conf.get(IndexType.DESTINATION, 0.0),
            research_confidence=per_index_conf.get(IndexType.RESEARCH, 0.0),
            # Raw documents (available for downstream engines)
            memory_documents=memory_docs,
            destination_documents=dest_docs,
            research_documents=research_docs,
            # Source metadata
            source_metadata=source_meta,
            # Provenance
            query=query,
            intent=intent,
            indexes_searched=indexes_searched,
            total_documents_retrieved=len(documents),
            execution_time_ms=execution_time_ms,
            cache_hit=cache_hit,
        )

        logger.debug(
            "ContextBuilder | intent=%s | mem=%d | dest=%d | research=%d | total=%d",
            intent.value,
            len(memory_docs),
            len(dest_docs),
            len(research_docs),
            len(documents),
        )
        return ctx

    # ------------------------------------------------------------------
    # Format methods (one per index type)
    # ------------------------------------------------------------------

    def _format_memory_block(self, docs: list[RetrievedDocument]) -> str:
        if not docs:
            return ""

        parts: list[str] = []
        for doc in docs[:_MAX_DOCS_PER_BLOCK]:
            source_label = self._source_label(doc.source_type)
            confidence_pct = int(doc.composite_score * 100)
            line = f"• [{source_label} | confidence {confidence_pct}%] {doc.content}"
            parts.append(line)

        block = "\n".join(parts)
        return block[:_MAX_BLOCK_CHARS]

    def _format_destination_block(self, docs: list[RetrievedDocument]) -> str:
        if not docs:
            return ""

        parts: list[str] = []
        for doc in docs[:_MAX_DOCS_PER_BLOCK]:
            name = doc.source_metadata.get("name") or doc.source_metadata.get("title", "")
            location = doc.source_metadata.get("location", "")
            score = doc.similarity_score

            if name and location:
                header = f"• {name} ({location}) [relevance {score:.0%}]"
            elif name:
                header = f"• {name} [relevance {score:.0%}]"
            else:
                header = f"• [relevance {score:.0%}]"

            line = f"{header}: {doc.content}"
            parts.append(line)

        block = "\n".join(parts)
        return block[:_MAX_BLOCK_CHARS]

    def _format_research_block(self, docs: list[RetrievedDocument]) -> str:
        if not docs:
            return ""

        parts: list[str] = []
        for doc in docs[:_MAX_DOCS_PER_BLOCK]:
            source = doc.source_metadata.get("source_title") or doc.source_type
            line = f"• [{source}] {doc.content}"
            parts.append(line)

        block = "\n".join(parts)
        return block[:_MAX_BLOCK_CHARS]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _source_label(source_type: str) -> str:
        labels = {
            "preference": "User Preference",
            "inferred_pref": "Inferred Preference",
            "behavioral": "Behavioral Pattern",
            "chat_memory": "Past Conversation",
            "diary_entry": "Diary Entry",
            "profile": "Profile",
            "trip_history": "Previous Trip",
            "poi": "Place of Interest",
            "activity": "Past Activity",
            "hotel": "Hotel",
            "restaurant": "Restaurant",
            "landmark": "Landmark",
            "research_paper": "Research",
            "tourism_guide": "Tourism Guide",
            "regulation": "Regulation",
            "historical": "Historical Record",
        }
        return labels.get(source_type, source_type.replace("_", " ").title())


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_builder: ContextBuilder | None = None


def get_context_builder() -> ContextBuilder:
    global _builder
    if _builder is None:
        from app.engines.ranking import get_ranker
        _builder = ContextBuilder(get_ranker())
    return _builder
