"""
Retrieval Cache for SmartTrip AI (SCIF Phase 5).

Two-tier cache:
  1. Embedding cache  — maps sha256(text) → list[float]
     Avoids re-calling the Gemini embedding API for identical strings.

  2. Search cache — maps sha256(query + sorted_indexes + top_k) → RetrievalResult
     Avoids re-running expensive parallel vector searches for identical queries.

Backends:
  - In-process dict (always available, zero dependencies)
  - Redis (activated when settings.REDIS_URL is set)

TTL:
  - In-process search cache: SEARCH_TTL_SECONDS (default 300 s)
  - Embedding cache: no TTL (embeddings are deterministic; same text → same vector)
  - Redis: uses key TTL matching the in-process TTL

Redis key schema:
  smarttrip:emb:<sha256_hex>          → JSON-encoded float list
  smarttrip:search:<sha256_hex>       → JSON-encoded RetrievalResult dict

Thread safety:
  The in-process dicts are accessed only from the asyncio event loop via
  await calls, so no locking is needed.  If the app is ever run with
  multiple threads sharing a loop (unusual for FastAPI/uvicorn), replace
  the dicts with asyncio.Lock-protected structures.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from app.engines.retrieval_models import CacheStats, RetrievalResult

logger = logging.getLogger(__name__)

SEARCH_TTL_SECONDS: int = 300          # 5 minutes
REDIS_EMB_PREFIX = "smarttrip:emb:"
REDIS_SEARCH_PREFIX = "smarttrip:search:"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _search_key(query: str, index_names: list[str], top_k: int) -> str:
    payload = f"{query}|{'|'.join(sorted(index_names))}|{top_k}"
    return _sha256(payload)


# ---------------------------------------------------------------------------
# In-process cache store
# ---------------------------------------------------------------------------

class _InProcessStore:
    """Simple time-aware in-process cache (no external dependency)."""

    def __init__(self) -> None:
        self._embeddings: dict[str, list[float]] = {}
        # search cache entries: (result, expiry_epoch)
        self._searches: dict[str, tuple[RetrievalResult, float]] = {}

    # Embedding
    def get_embedding(self, key: str) -> list[float] | None:
        return self._embeddings.get(key)

    def set_embedding(self, key: str, vector: list[float]) -> None:
        self._embeddings[key] = vector

    # Search results
    def get_search(self, key: str) -> RetrievalResult | None:
        entry = self._searches.get(key)
        if entry is None:
            return None
        result, expiry = entry
        if time.monotonic() > expiry:
            del self._searches[key]
            return None
        return result

    def set_search(self, key: str, result: RetrievalResult, ttl: int = SEARCH_TTL_SECONDS) -> None:
        self._searches[key] = (result, time.monotonic() + ttl)

    def clear(self) -> None:
        self._embeddings.clear()
        self._searches.clear()

    @property
    def embedding_count(self) -> int:
        return len(self._embeddings)

    @property
    def search_count(self) -> int:
        # Evict expired before counting
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._searches.items() if now > exp]
        for k in expired:
            del self._searches[k]
        return len(self._searches)


# ---------------------------------------------------------------------------
# Redis store (optional)
# ---------------------------------------------------------------------------

class _RedisStore:
    """
    Redis-backed cache layer.  Constructed only when REDIS_URL is set.
    Falls back gracefully: if any Redis operation raises, it logs a warning
    and returns None / does nothing so the caller falls through to the
    in-process store.
    """

    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as aioredis  # type: ignore[import]
        self._client = aioredis.from_url(redis_url, decode_responses=True)
        logger.info("RetrievalCache: Redis backend initialised at %s", redis_url)

    async def get_embedding(self, key: str) -> list[float] | None:
        try:
            raw = await self._client.get(REDIS_EMB_PREFIX + key)
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.warning("Redis embedding get failed: %s", exc)
            return None

    async def set_embedding(self, key: str, vector: list[float]) -> None:
        try:
            await self._client.set(REDIS_EMB_PREFIX + key, json.dumps(vector))
        except Exception as exc:
            logger.warning("Redis embedding set failed: %s", exc)

    async def get_search(self, key: str) -> RetrievalResult | None:
        try:
            raw = await self._client.get(REDIS_SEARCH_PREFIX + key)
            if raw is None:
                return None
            data = json.loads(raw)
            return RetrievalResult.model_validate(data)
        except Exception as exc:
            logger.warning("Redis search get failed: %s", exc)
            return None

    async def set_search(
        self, key: str, result: RetrievalResult, ttl: int = SEARCH_TTL_SECONDS
    ) -> None:
        try:
            await self._client.setex(
                REDIS_SEARCH_PREFIX + key,
                ttl,
                result.model_dump_json(),
            )
        except Exception as exc:
            logger.warning("Redis search set failed: %s", exc)


# ---------------------------------------------------------------------------
# Public cache façade
# ---------------------------------------------------------------------------

class RetrievalCache:
    """
    Public cache used by RetrievalEngine.

    API:
        await cache.get_embedding(text) -> list[float] | None
        await cache.set_embedding(text, vector)
        await cache.get_search_result(query, index_names, top_k) -> RetrievalResult | None
        await cache.set_search_result(query, index_names, top_k, result)
        cache.stats() -> CacheStats
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._local = _InProcessStore()
        self._redis: _RedisStore | None = None
        if redis_url:
            try:
                self._redis = _RedisStore(redis_url)
            except Exception as exc:
                logger.warning(
                    "RetrievalCache: Redis init failed (%s) — using in-process cache only", exc
                )
        self._stats = CacheStats()

    # ------------------------------------------------------------------ #
    # Embedding cache
    # ------------------------------------------------------------------ #

    async def get_embedding(self, text: str) -> list[float] | None:
        key = _sha256(text)

        # L1 — in-process
        vector = self._local.get_embedding(key)
        if vector is not None:
            self._stats.embedding_hits += 1
            return vector

        # L2 — Redis
        if self._redis:
            vector = await self._redis.get_embedding(key)
            if vector is not None:
                self._local.set_embedding(key, vector)   # promote to L1
                self._stats.embedding_hits += 1
                return vector

        self._stats.embedding_misses += 1
        return None

    async def set_embedding(self, text: str, vector: list[float]) -> None:
        key = _sha256(text)
        self._local.set_embedding(key, vector)
        if self._redis:
            await self._redis.set_embedding(key, vector)

    # ------------------------------------------------------------------ #
    # Search result cache
    # ------------------------------------------------------------------ #

    async def get_search_result(
        self,
        query: str,
        index_names: list[str],
        top_k: int,
    ) -> RetrievalResult | None:
        key = _search_key(query, index_names, top_k)

        # L1 — in-process
        result = self._local.get_search(key)
        if result is not None:
            self._stats.search_hits += 1
            return result

        # L2 — Redis
        if self._redis:
            result = await self._redis.get_search(key)
            if result is not None:
                self._local.set_search(key, result)     # promote to L1
                self._stats.search_hits += 1
                return result

        self._stats.search_misses += 1
        return None

    async def set_search_result(
        self,
        query: str,
        index_names: list[str],
        top_k: int,
        result: RetrievalResult,
        ttl: int = SEARCH_TTL_SECONDS,
    ) -> None:
        key = _search_key(query, index_names, top_k)
        self._local.set_search(key, result, ttl)
        if self._redis:
            await self._redis.set_search(key, result, ttl)

    # ------------------------------------------------------------------ #
    # Stats & housekeeping
    # ------------------------------------------------------------------ #

    def stats(self) -> CacheStats:
        return self._stats

    def clear(self) -> None:
        self._local.clear()
        self._stats = CacheStats()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_cache: RetrievalCache | None = None


def get_retrieval_cache() -> RetrievalCache:
    """
    Returns the process-level singleton RetrievalCache, auto-configured
    from settings.REDIS_URL.  Import settings lazily to avoid circular
    imports at module load time.
    """
    global _cache
    if _cache is None:
        from app.core.config import get_settings
        settings = get_settings()
        _cache = RetrievalCache(redis_url=settings.REDIS_URL)
    return _cache
