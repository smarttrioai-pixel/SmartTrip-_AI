"""
Retrieval Router for SmartTrip AI (SCIF Phase 5).

Classifies the intent of an incoming query using deterministic keyword
heuristics — no LLM call, no network, zero latency — and returns the set
of IndexType values that should be searched for that intent.

Design:
  - Stateless: no instance state, safe to share across threads/requests.
  - Transparent: every routing decision is logged at DEBUG level with the
    matched signals so it's auditable in production logs.
  - Extensible: add new intents and keyword sets without touching anything
    else in the engine.

Routing table:
  TRAVEL_PLANNING        → [DESTINATION]
  USER_PERSONALIZATION   → [MEMORY]
  ACADEMIC_RESEARCH      → [RESEARCH]
  CHAT                   → [MEMORY, DESTINATION]
  GENERAL_RECOMMENDATION → [MEMORY, DESTINATION, RESEARCH]
"""
from __future__ import annotations

import logging
import re
from typing import NamedTuple

from app.engines.retrieval_models import IndexType, QueryIntent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keyword signal sets (all lowercased for fast substring matching)
# ---------------------------------------------------------------------------

_TRAVEL_PLANNING_SIGNALS = frozenset({
    "plan", "itinerary", "trip", "travel", "visit", "tour", "journey",
    "schedule", "day by day", "day-by-day", "route", "destination",
    "flight", "hotel", "accommodation", "book", "booking", "budget",
    "days", "nights", "week", "weekend", "holiday", "vacation",
    "sightseeing", "activities", "what to do", "where to go",
    "how to get", "transport", "navigate",
})

_USER_PERSONALIZATION_SIGNALS = frozenset({
    "my preference", "my taste", "i like", "i love", "i prefer",
    "i usually", "i always", "based on me", "my history", "my style",
    "remember", "last time", "previously", "before", "profile",
    "my budget", "my diet", "vegetarian", "vegan", "halal", "kosher",
    "wheelchair", "accessibility", "my interest", "personaliz",
    "customiz", "tailor", "recommend for me",
})

_ACADEMIC_RESEARCH_SIGNALS = frozenset({
    "research", "paper", "study", "academic", "ieee", "journal",
    "sustainable", "sustainability", "ecology", "environmental",
    "policy", "regulation", "law", "rule", "permit", "visa",
    "statistics", "data", "analysis", "findings", "evidence",
    "heritage", "unesco", "conservation", "historical context",
    "literature review", "citation", "reference",
})

_CHAT_SIGNALS = frozenset({
    "what", "how", "why", "when", "where", "who", "which",
    "tell me", "explain", "help", "advice", "suggest", "can you",
    "could you", "should i", "is there", "are there", "do you know",
})

# ---------------------------------------------------------------------------
# Routing result
# ---------------------------------------------------------------------------

class RoutingDecision(NamedTuple):
    intent: QueryIntent
    indexes: list[IndexType]
    matched_signals: list[str]       # signals that triggered this decision
    confidence: float                # 0–1; higher = stronger signal match


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class RetrievalRouter:
    """
    Deterministic, heuristic-based query router.

    Usage:
        router = RetrievalRouter()
        intent, indexes = router.route("Plan me a 5-day trip to Kyoto")
        # → (QueryIntent.TRAVEL_PLANNING, [IndexType.DESTINATION])
    """

    def route(self, query: str) -> tuple[QueryIntent, list[IndexType]]:
        decision = self._classify(query)
        logger.debug(
            "RetrievalRouter | query=%r | intent=%s | indexes=%s | signals=%s | confidence=%.2f",
            query[:80],
            decision.intent.value,
            [i.value for i in decision.indexes],
            decision.matched_signals[:5],
            decision.confidence,
        )
        return decision.intent, decision.indexes

    def route_verbose(self, query: str) -> RoutingDecision:
        """Return the full RoutingDecision (useful for logging/explainability)."""
        return self._classify(query)

    # ------------------------------------------------------------------
    # Internal classification logic
    # ------------------------------------------------------------------

    def _classify(self, query: str) -> RoutingDecision:
        normalized = self._normalize(query)
        tokens = set(re.findall(r"\b\w+\b", normalized))
        words = normalized  # for substring matching

        # --- Score each signal group ---
        travel_hits = self._match(tokens, words, _TRAVEL_PLANNING_SIGNALS)
        personal_hits = self._match(tokens, words, _USER_PERSONALIZATION_SIGNALS)
        research_hits = self._match(tokens, words, _ACADEMIC_RESEARCH_SIGNALS)
        chat_hits = self._match(tokens, words, _CHAT_SIGNALS)

        travel_score = len(travel_hits)
        personal_score = len(personal_hits)
        research_score = len(research_hits)

        # --- Decision rules (ordered: most specific → most general) ---

        # Pure academic / research query
        if research_score >= 2 and research_score > travel_score:
            return RoutingDecision(
                intent=QueryIntent.ACADEMIC_RESEARCH,
                indexes=[IndexType.RESEARCH],
                matched_signals=list(research_hits),
                confidence=min(1.0, research_score / 4),
            )

        # Pure personalization (no place signals)
        if personal_score >= 2 and travel_score == 0:
            return RoutingDecision(
                intent=QueryIntent.USER_PERSONALIZATION,
                indexes=[IndexType.MEMORY],
                matched_signals=list(personal_hits),
                confidence=min(1.0, personal_score / 4),
            )

        # Strong travel planning intent
        if travel_score >= 2 and personal_score <= 1 and research_score <= 1:
            return RoutingDecision(
                intent=QueryIntent.TRAVEL_PLANNING,
                indexes=[IndexType.DESTINATION],
                matched_signals=list(travel_hits),
                confidence=min(1.0, travel_score / 5),
            )

        # Travel + personalization → chat-like rich retrieval
        if travel_score >= 1 or personal_score >= 1:
            combined_signals = list(travel_hits | personal_hits)
            return RoutingDecision(
                intent=QueryIntent.CHAT,
                indexes=[IndexType.MEMORY, IndexType.DESTINATION],
                matched_signals=combined_signals,
                confidence=min(1.0, (travel_score + personal_score) / 6),
            )

        # Any question-like query → chat (memory + destination)
        if chat_hits:
            return RoutingDecision(
                intent=QueryIntent.CHAT,
                indexes=[IndexType.MEMORY, IndexType.DESTINATION],
                matched_signals=list(chat_hits),
                confidence=0.4,
            )

        # Default: search everything
        return RoutingDecision(
            intent=QueryIntent.GENERAL_RECOMMENDATION,
            indexes=[IndexType.MEMORY, IndexType.DESTINATION, IndexType.RESEARCH],
            matched_signals=[],
            confidence=0.3,
        )

    @staticmethod
    def _normalize(text: str) -> str:
        return text.lower().strip()

    @staticmethod
    def _match(tokens: set[str], full_text: str, signals: frozenset[str]) -> set[str]:
        """Return all signals that appear either as a word token or a substring."""
        hits: set[str] = set()
        for signal in signals:
            # Multi-word signals: substring match
            if " " in signal:
                if signal in full_text:
                    hits.add(signal)
            else:
                # Single-word: token match (avoids partial-word false positives)
                if signal in tokens:
                    hits.add(signal)
        return hits


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_router: RetrievalRouter | None = None


def get_retrieval_router() -> RetrievalRouter:
    global _router
    if _router is None:
        _router = RetrievalRouter()
    return _router
