"""
Retrieval Engine for SmartTrip AI (SCIF Phase 5).

This is THE single entry point for every vector-search and retrieval
operation in the system.  No other module should import from
app.integrations.faiss_vector_store or call embed_text directly.

Architecture:
  RetrievalEngine
    ├── RetrievalRouter   — classify query intent → select indexes
    ├── RetrievalCache    — embedding + search result cache (in-process + Redis)
    ├── VectorIndexManager — three named parallel-searchable indexes
    │     ├── MemoryVectorIndex      — user preferences, trips, chat history
    │     ├── DestinationVectorIndex — POIs, activities, hotels, landmarks
    │     └── ResearchVectorIndex   — academic papers, tourism knowledge
    ├── Ranker            — multi-factor ranking + deduplication
    └── ContextBuilder    — assemble StructuredContext for Gemini

Public API:
    retrieve(request)               → RetrievalResult
    retrieve_context(...)           → StructuredContext
    retrieve_places(...)            → RetrievalResult
    retrieve_user_memory(...)       → RetrievalResult
    retrieve_trip_history(...)      → RetrievalResult
    retrieve_research(...)          → RetrievalResult
    retrieve_for_chat(...)          → StructuredContext

    # Index population
    index_user_memory(user_id, longterm_memory)
    index_place(place_data)
    index_research_document(text, metadata)
    index_trip(user_id, trip)

Every method is fully async.  Logging covers: query, selected indexes,
candidate count, final count, similarity scores, execution time, cache
hit/miss.  This satisfies SCIF Phase 5 Task 11 (Logging).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.engines.context_builder import ContextBuilder, get_context_builder
from app.engines.ranking import Ranker, get_ranker
from app.engines.retrieval_cache import RetrievalCache, get_retrieval_cache
from app.engines.retrieval_models import (
    IndexType,
    QueryIntent,
    RetrievalRequest,
    RetrievalResult,
    RetrievedDocument,
    StructuredContext,
)
from app.engines.retrieval_router import RetrievalRouter, get_retrieval_router
from app.engines.vector_indexes import VectorIndexManager, get_vector_index_manager
from app.integrations.embeddings import (
    embed_document,
    embed_query,
    EMBEDDING_DIMENSION,
)

logger = logging.getLogger(__name__)


class RetrievalEngine:
    """
    Production-quality cognitive retrieval engine.

    Constructed via dependency injection (see api/deps.py).
    All dependencies are injected so tests can substitute mocks.

    The engine is intentionally stateless with respect to per-request data —
    all shared state (indexes, cache) lives in the injected singletons.
    """

    def __init__(
        self,
        index_manager: VectorIndexManager,
        router: RetrievalRouter,
        cache: RetrievalCache,
        ranker: Ranker,
        context_builder: ContextBuilder,
    ) -> None:
        self._indexes = index_manager
        self._router = router
        self._cache = cache
        self._ranker = ranker
        self._builder = context_builder

    # ==================================================================
    # Primary public API
    # ==================================================================

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """
        Full retrieval pipeline:
          embed → route → parallel search → rank → deduplicate → cache → return.
        """
        start = time.perf_counter()

        # --- Determine indexes to search ---
        if request.forced_intent and request.index_types:
            intent = request.forced_intent
            indexes = request.index_types
        elif request.index_types:
            intent = request.forced_intent or QueryIntent.GENERAL_RECOMMENDATION
            indexes = request.index_types
        else:
            intent, indexes = self._router.route(request.query)

        index_names = [i.value for i in indexes]

        # --- Cache check (search-level) ---
        if not request.bypass_cache:
            cached = await self._cache.get_search_result(request.query, index_names, request.top_k)
            if cached is not None:
                elapsed = (time.perf_counter() - start) * 1000
                logger.info(
                    "RetrievalEngine.retrieve | CACHE HIT | query=%r | intent=%s | "
                    "indexes=%s | elapsed_ms=%.1f",
                    request.query[:60], intent.value, index_names, elapsed,
                )
                cached.cache_hit = True
                cached.execution_time_ms = elapsed
                return cached

        # --- Embed query (with embedding cache) ---
        # RuntimeError from embed_query() is re-raised here with added context.
        # The SCIF engines (MemoryEngine, PlanningEngine, ChatService) all have
        # their own try/except that catches this and logs a warning, so a
        # transient API failure gracefully skips retrieval rather than crashing
        # the entire request.  We deliberately do NOT swallow the error here —
        # an empty context is much better than silently wrong context.
        try:
            query_vector = await self._get_embedding(request.query)
        except RuntimeError as exc:
            raise RuntimeError(
                f"RetrievalEngine.retrieve: embedding failed for query={request.query!r:.60} | {exc}"
            ) from exc

        # --- Parallel vector search ---
        candidates = await self._indexes.search_parallel(
            query_vector,
            indexes,
            top_k=request.top_k * 3,     # fetch 3× so ranker has room to deduplicate
            min_score=request.min_similarity,
            user_interests=request.user_interests,
        )
        total_candidates = len(candidates)

        # --- Rank + deduplicate ---
        ranked = self._ranker.rank_and_deduplicate(candidates, top_k=request.top_k)
        confidence = self._ranker.compute_confidence(ranked)

        elapsed = (time.perf_counter() - start) * 1000

        result = RetrievalResult(
            documents=ranked,
            query=request.query,
            indexes_searched=indexes,
            intent=intent,
            total_candidates=total_candidates,
            returned_count=len(ranked),
            confidence=confidence,
            execution_time_ms=round(elapsed, 2),
            cache_hit=False,
        )

        # --- Store in cache ---
        if not request.bypass_cache:
            await self._cache.set_search_result(request.query, index_names, request.top_k, result)

        # --- Structured log ---
        self._log_retrieval(request.query, intent, indexes, ranked, elapsed, cache_hit=False)

        return result

    async def retrieve_context(
        self,
        user_id: str,
        query: str,
        *,
        chat_id: str | None = None,
        top_k: int = 8,
        user_interests: list[str] | None = None,
        bypass_cache: bool = False,
    ) -> StructuredContext:
        """
        High-level retrieval that returns a StructuredContext ready for
        Gemini prompt injection.  Searches Memory + Destination by default
        (CHAT routing).  Drop-in replacement for MemoryEngine.get_context().
        """
        request = RetrievalRequest(
            query=query,
            user_id=user_id,
            chat_id=chat_id,
            top_k=top_k,
            user_interests=user_interests or [],
            bypass_cache=bypass_cache,
        )
        result = await self.retrieve(request)
        return self._builder.build(
            documents=result.documents,
            query=query,
            intent=result.intent,
            indexes_searched=result.indexes_searched,
            execution_time_ms=result.execution_time_ms,
            cache_hit=result.cache_hit,
        )

    async def retrieve_for_chat(
        self,
        user_id: str,
        query: str,
        chat_id: str | None = None,
        *,
        top_k: int = 8,
        user_interests: list[str] | None = None,
    ) -> StructuredContext:
        """
        Chat-optimised retrieval: always searches MEMORY + DESTINATION,
        giving the chat engine a rich context of user preferences and
        relevant places.
        """
        request = RetrievalRequest(
            query=query,
            user_id=user_id,
            chat_id=chat_id,
            index_types=[IndexType.MEMORY, IndexType.DESTINATION],
            forced_intent=QueryIntent.CHAT,
            top_k=top_k,
            user_interests=user_interests or [],
        )
        result = await self.retrieve(request)
        return self._builder.build(
            documents=result.documents,
            query=query,
            intent=QueryIntent.CHAT,
            indexes_searched=result.indexes_searched,
            execution_time_ms=result.execution_time_ms,
            cache_hit=result.cache_hit,
        )

    async def retrieve_user_memory(
        self,
        user_id: str,
        query: str,
        *,
        top_k: int = 10,
        user_interests: list[str] | None = None,
    ) -> RetrievalResult:
        """Retrieve from the Memory index only."""
        request = RetrievalRequest(
            query=query,
            user_id=user_id,
            index_types=[IndexType.MEMORY],
            forced_intent=QueryIntent.USER_PERSONALIZATION,
            top_k=top_k,
            user_interests=user_interests or [],
            min_similarity=0.40,   # slightly looser for memory — surface more context
        )
        return await self.retrieve(request)

    async def retrieve_trip_history(
        self,
        user_id: str,
        query: str,
        *,
        top_k: int = 5,
    ) -> RetrievalResult:
        """Retrieve trip-history documents from the Memory index."""
        request = RetrievalRequest(
            query=query,
            user_id=user_id,
            index_types=[IndexType.MEMORY],
            forced_intent=QueryIntent.USER_PERSONALIZATION,
            top_k=top_k,
            min_similarity=0.35,
        )
        result = await self.retrieve(request)
        # Filter to trip_history source_type only
        result.documents = [
            d for d in result.documents if d.source_type in ("trip_history", "preference")
        ]
        result.returned_count = len(result.documents)
        return result

    async def retrieve_places(
        self,
        query: str,
        *,
        lat: float | None = None,
        lon: float | None = None,
        top_k: int = 8,
        user_interests: list[str] | None = None,
    ) -> RetrievalResult:
        """Retrieve from the Destination index only."""
        request = RetrievalRequest(
            query=query,
            index_types=[IndexType.DESTINATION],
            forced_intent=QueryIntent.TRAVEL_PLANNING,
            top_k=top_k,
            user_interests=user_interests or [],
            min_similarity=0.40,
        )
        return await self.retrieve(request)

    async def retrieve_research(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> RetrievalResult:
        """Retrieve from the Research index only."""
        request = RetrievalRequest(
            query=query,
            index_types=[IndexType.RESEARCH],
            forced_intent=QueryIntent.ACADEMIC_RESEARCH,
            top_k=top_k,
            min_similarity=0.40,
        )
        return await self.retrieve(request)

    # ==================================================================
    # Index population methods
    # ==================================================================

    async def index_user_memory(
        self,
        user_id: str,
        longterm_memory: Any,  # app.models.memory.LongTermMemory
    ) -> None:
        """
        Sync a user's LongTermMemory into the MemoryVectorIndex.
        Called by MemoryEngine.save_preference() to keep the index
        up to date without a full rebuild.

        Clears existing entries for this user (keyed by user_id in metadata)
        before re-adding — avoids accumulating stale duplicates.
        """
        # Clear all docs for this user first
        existing_meta = self._indexes.memory._metadata
        existing_vectors = list(self._indexes.memory._vectors) if self._indexes.memory.size > 0 else []

        # Rebuild without this user's docs (simple O(n) filter)
        import numpy as np
        keep_vecs: list[list[float]] = []
        keep_meta: list[dict] = []
        for i, meta in enumerate(existing_meta):
            if meta.get("user_id") != user_id:
                keep_vecs.append(existing_vectors[i] if i < len(existing_vectors) else [])
                keep_meta.append(meta)

        dim = self._indexes.memory._dimension
        if keep_vecs:
            self._indexes.memory._vectors = np.array(keep_vecs, dtype=np.float32)
        else:
            self._indexes.memory._vectors = np.empty((0, dim), dtype=np.float32)
        self._indexes.memory._metadata = keep_meta

        # Add all embeddings from longterm memory
        added = 0
        for emb in longterm_memory.embeddings:
            if not emb.vector:
                continue
            self._indexes.memory.add(
                text=emb.source_text,
                vector=emb.vector,
                metadata={
                    "user_id": user_id,
                    "source_type": emb.source_type or "preference",
                    "importance": emb.weight,
                    "timestamp": emb.created_at,
                    "embedding_id": emb.id,
                },
            )
            added += 1

        # Add inferred preferences — these have no pre-computed vector,
        # embed them as documents
        for pref in getattr(longterm_memory, "inferred_preferences", []):
            if getattr(pref, "status", "active") != "active":
                continue
            try:
                vector = await self._get_document_embedding(pref.statement)
            except Exception as exc:
                logger.error(
                    "RetrievalEngine.index_user_memory | embedding inferred_pref failed "
                    "(user=%s, pref=%r): %s",
                    user_id, pref.statement[:60], exc,
                )
                continue  # skip this preference; don't abort the whole batch
            self._indexes.memory.add(
                text=pref.statement,
                vector=vector,
                metadata={
                    "user_id": user_id,
                    "source_type": "inferred_pref",
                    "importance": getattr(pref, "confidence", 0.8),
                    "timestamp": getattr(pref, "promoted_at", None),
                },
            )
            added += 1

        logger.info(
            "RetrievalEngine.index_user_memory | user=%s | indexed=%d docs",
            user_id, added,
        )

    async def index_place(self, place_data: dict[str, Any]) -> None:
        """
        Add a single place to the DestinationVectorIndex.
        Accepts the shape returned by OpenTripMapService.get_place_details()
        or PlaceEnrichmentService.enrich_place().
        """
        name = place_data.get("matched_place_name") or place_data.get("name", "")
        description = place_data.get("wikipedia_summary") or place_data.get("description", "")
        category = place_data.get("category") or place_data.get("kinds", [""])[0] if isinstance(place_data.get("kinds"), list) else ""
        address = place_data.get("address", "")

        # Build indexable text
        text_parts = [p for p in [name, category, description, address] if p]
        if not text_parts:
            return
        text = " | ".join(text_parts[:3])[:500]   # cap at 500 chars

        vector = await self._get_document_embedding(text, title=name or None)

        source_type = "poi"
        if category:
            cl = category.lower()
            if "hotel" in cl or "accommodation" in cl:
                source_type = "hotel"
            elif "restaurant" in cl or "food" in cl or "cafe" in cl:
                source_type = "restaurant"
            elif "museum" in cl or "gallery" in cl:
                source_type = "landmark"

        self._indexes.destination.add(
            text=text,
            vector=vector,
            metadata={
                "source_type": source_type,
                "name": name,
                "lat": place_data.get("lat"),
                "lon": place_data.get("lon"),
                "rating": place_data.get("rating"),
                "image_url": place_data.get("image_url"),
                "address": address,
                "importance": min(1.0, float(place_data.get("rating") or 3) / 7.0),
            },
        )
        logger.debug("RetrievalEngine.index_place | name=%s | type=%s", name, source_type)

    async def index_trip(self, user_id: str, trip: Any) -> None:
        """
        Index a saved trip into the Memory index as 'trip_history'.
        Accepts the Trip model from app.models.trip.
        """
        destination = getattr(trip, "destination", "")
        style = getattr(trip, "travel_style", "")
        budget = getattr(trip, "budget", 0)
        currency = getattr(trip, "currency", "USD")
        days = getattr(trip, "days", [])
        num_days = len(days) if days else 0

        summary = (
            f"Previously visited {destination} for {num_days} days "
            f"({style} style, budget {budget} {currency})."
        )

        # Add activity highlights
        highlights: list[str] = []
        for day in days[:3]:
            for act in (day.get("activities", []) if isinstance(day, dict) else [])[:2]:
                title = act.get("title", "") if isinstance(act, dict) else ""
                if title:
                    highlights.append(title)
        if highlights:
            summary += f" Activities included: {', '.join(highlights[:4])}."

        vector = await self._get_document_embedding(summary, title=f"Trip to {destination}")
        self._indexes.memory.add(
            text=summary,
            vector=vector,
            metadata={
                "user_id": user_id,
                "source_type": "trip_history",
                "destination": destination,
                "travel_style": style,
                "budget": budget,
                "importance": 0.9,
                "trip_id": getattr(trip, "id", ""),
            },
        )
        logger.debug("RetrievalEngine.index_trip | user=%s | destination=%s", user_id, destination)

    async def index_research_document(
        self, text: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """
        Add a research document (paper chunk, tourism guide, regulation)
        to the ResearchVectorIndex.
        """
        if not text.strip():
            return
        vector = await self._get_document_embedding(text[:8000])  # embed_document truncates at 8000 chars
        self._indexes.research.add(
            text=text,
            vector=vector,
            metadata={
                "source_type": (metadata or {}).get("source_type", "research_paper"),
                **(metadata or {}),
            },
        )
        logger.debug(
            "RetrievalEngine.index_research_document | type=%s | len=%d",
            (metadata or {}).get("source_type", "?"),
            len(text),
        )

    # ==================================================================
    # Utility / introspection
    # ==================================================================

    def index_stats(self) -> dict[str, Any]:
        """Return size of each index and cache stats."""
        return {
            "indexes": self._indexes.stats(),
            "cache": self._cache.stats().to_dict(),
        }

    # ==================================================================
    # Internal helpers
    # ==================================================================

    async def _get_embedding(self, text: str) -> list[float]:
        """
        Embed a *query* string with a two-tier cache check first.

        Uses task_type=RETRIEVAL_QUERY (correct for search strings that will
        be compared against indexed RETRIEVAL_DOCUMENT vectors).

        Raises RuntimeError on embedding failure — no silent zero-vector
        fallback.  Callers in the retrieve() pipeline are wrapped in
        try/except so a transient API failure surfaces as a 503 with a
        clear message rather than silently degrading retrieval to zero
        similarity for every document.
        """
        cached = await self._cache.get_embedding(text)
        if cached is not None:
            return cached

        # Will raise RuntimeError (with full diagnostic) on API failure.
        # Do NOT catch here — let it propagate so the caller can decide
        # whether to surface a 503 or return an empty result with a warning.
        vector = await embed_query(text)

        await self._cache.set_embedding(text, vector)
        return vector

    async def _get_document_embedding(self, text: str, title: str | None = None) -> list[float]:
        """
        Embed a *document* string to store in a vector index.

        Uses task_type=RETRIEVAL_DOCUMENT so vectors are geometrically
        aligned with RETRIEVAL_QUERY vectors for accurate cosine similarity.
        Results are cached identically to query embeddings (same cache key
        = same text, so if a query and document happen to share identical
        text, the cached vector is reused regardless of task type — this
        is an acceptable trade-off at this scale).
        """
        # Use text as cache key — if already cached from a previous embed
        # (e.g. from a query), reuse it to avoid an extra API call.
        cached = await self._cache.get_embedding(text)
        if cached is not None:
            return cached

        vector = await embed_document(text, title=title)

        await self._cache.set_embedding(text, vector)
        return vector

    def _log_retrieval(
        self,
        query: str,
        intent: QueryIntent,
        indexes: list[IndexType],
        documents: list[RetrievedDocument],
        elapsed_ms: float,
        cache_hit: bool,
    ) -> None:
        """Structured retrieval log — covers SCIF Task 11 requirements."""
        scores = [round(d.similarity_score, 3) for d in documents[:5]]
        logger.info(
            "RetrievalEngine | query=%r | intent=%s | indexes=%s | "
            "returned=%d | top_scores=%s | elapsed_ms=%.1f | cache=%s",
            query[:60],
            intent.value,
            [i.value for i in indexes],
            len(documents),
            scores,
            elapsed_ms,
            "HIT" if cache_hit else "MISS",
        )


# ===========================================================================
# Module-level singleton factory
# ===========================================================================

_engine: RetrievalEngine | None = None


def get_retrieval_engine() -> RetrievalEngine:
    """
    Returns the process-level singleton RetrievalEngine, constructed with
    all singleton dependencies.  Safe to call from FastAPI Depends().
    """
    global _engine
    if _engine is None:
        _engine = RetrievalEngine(
            index_manager=get_vector_index_manager(),
            router=get_retrieval_router(),
            cache=get_retrieval_cache(),
            ranker=get_ranker(),
            context_builder=get_context_builder(),
        )
    return _engine
