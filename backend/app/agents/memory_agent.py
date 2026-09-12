"""
MemoryAgent for SmartTrip AI (SCIF Framework).

Thin agent interface around MemoryEngine and its Firestore-backed repositories.
Responsible for retrieving and summarizing persistent user memory for
injection into the CognitivePlanningContext BEFORE Qwen generates.

Data sources:
    - Firestore: memory_longterm/{user_id}  (preference embeddings)
    - Firestore: memory_behavioral/{user_id} (behavioral feature weights)

Design rules:
- Never fabricate preferences. If memory is empty, return empty context.
- Wrap exceptions so a memory retrieval failure doesn't abort generation.
- The contribution_summary in AgentOutput must be safe to expose (no PIIs).
"""
from __future__ import annotations

import logging
import time

from app.cognitive.live_context import AgentOutput
from app.cognitive.memory_engine import MemoryContext, MemoryEngine

logger = logging.getLogger(__name__)


class MemoryAgent:
    """
    SCIF Planning Agent — Persistent Memory Retrieval.

    Wraps MemoryEngine. Runs BEFORE Qwen.
    Retrieves long-term preferences and behavioral weights from Firestore.
    """

    def __init__(self, memory_engine: MemoryEngine) -> None:
        self._engine = memory_engine

    async def retrieve(
        self,
        user_id: str,
        query: str,
    ) -> tuple[MemoryContext | None, AgentOutput]:
        """
        Retrieve memory context for the given user and planning query.

        Returns:
            (MemoryContext | None, AgentOutput)
            MemoryContext is None on failure (non-fatal — generation continues).
        """
        t0 = time.monotonic()

        try:
            memory_ctx = await self._engine.get_context(user_id, query)
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "MEMORY_AGENT user_id=%s error: %s (non-fatal)", user_id, exc
            )
            agent_output = AgentOutput(
                agent_name="MemoryAgent",
                status="error",
                data_source="Firestore/memory_longterm",
                contribution_summary=f"Memory retrieval failed: {exc}",
                items_returned=0,
                latency_ms=latency_ms,
                details={"error": str(exc)},
            )
            return None, agent_output

        latency_ms = (time.monotonic() - t0) * 1000
        num_preferences = len(memory_ctx.relevant_preferences) if memory_ctx else 0

        # Build a safe contribution summary (no PII or raw embedding data)
        if memory_ctx and num_preferences > 0:
            # Show only first few preference texts, truncated
            sample = [
                (p.value[:60] if hasattr(p, "value") else str(p)[:60])
                for p in memory_ctx.relevant_preferences[:3]
            ]
            contribution = (
                f"{num_preferences} relevant preference(s) retrieved from Firestore. "
                f"Sample: {'; '.join(sample)}"
            )
        elif memory_ctx:
            contribution = "Memory retrieved but no relevant preferences found for this query."
        else:
            contribution = "No memory context available (new user or first trip)."

        logger.info(
            "MEMORY_AGENT user_id=%s preferences=%d latency_ms=%.0f",
            user_id, num_preferences, latency_ms,
        )

        # Behavioral feature weights summary
        feature_weights: dict[str, float] = {}
        if memory_ctx and hasattr(memory_ctx, "behavioral") and memory_ctx.behavioral:
            feature_weights = memory_ctx.behavioral.feature_weights or {}

        agent_output = AgentOutput(
            agent_name="MemoryAgent",
            status="ok",
            data_source="Firestore/memory_longterm",
            contribution_summary=contribution,
            items_returned=num_preferences,
            latency_ms=latency_ms,
            details={
                "preferences_retrieved": num_preferences,
                "has_behavioral": bool(feature_weights),
                "feature_weight_keys": list(feature_weights.keys()),
            },
        )

        return memory_ctx, agent_output
