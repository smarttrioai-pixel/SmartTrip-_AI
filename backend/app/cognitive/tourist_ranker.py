"""
Tourist Relevance Ranker for SmartTrip AI.

Scores PlaceCandidate objects for attraction slots using a composite formula
that rewards genuine tourist destinations and penalizes generic businesses.

Design goals:
    - A temple/museum/landmark ALWAYS outranks a juice shop for an attraction slot.
    - Generic commercial businesses receive a hard penalty.
    - User memory preferences (history, nature, temples, etc.) influence ranking.
    - Rating and review count add signal when available (not fabricated).
    - Duplicates are penalized via place_id tracking.

This is a SCIF cognitive scoring component.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from app.integrations.google_places_provider import TOURIST_TYPES, COMMERCIAL_TYPES
from app.integrations.place_provider import PlaceCandidate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Minimum scores
# ---------------------------------------------------------------------------

# Attraction candidates below this tourist relevance score are rejected.
# This prevents generic businesses from appearing in attraction slots.
MIN_TOURIST_RELEVANCE = 0.35

# Penalties
DUPLICATE_PENALTY = 0.40
COMMERCIAL_PENALTY = 0.50

# User preference keyword → Google type mapping
# Used to boost candidates matching user memory preferences
_PREFERENCE_TYPE_MAP: dict[str, list[str]] = {
    "history": ["historical_landmark", "museum", "ruins", "fort", "palace", "castle", "monument"],
    "historical": ["historical_landmark", "museum", "ruins", "fort", "palace", "castle"],
    "temple": ["hindu_temple", "jain_temple", "buddhist_temple", "mosque", "church", "place_of_worship"],
    "religious": ["hindu_temple", "jain_temple", "buddhist_temple", "mosque", "church", "place_of_worship"],
    "nature": ["national_park", "park", "wildlife_refuge", "nature_preserve", "garden", "botanical_garden", "waterfall", "lake"],
    "heritage": ["historical_landmark", "museum", "ruins", "fort", "palace"],
    "art": ["art_gallery", "museum", "cultural_center", "performing_arts_theater"],
    "culture": ["cultural_center", "museum", "art_gallery", "historical_landmark"],
    "wildlife": ["zoo", "aquarium", "wildlife_refuge", "national_park"],
    "adventure": ["amusement_park", "national_park", "park"],
    "architecture": ["historical_landmark", "palace", "fort", "church", "mosque"],
    "shopping": ["shopping_mall"],
    "relaxed": ["park", "garden", "botanical_garden", "beach"],
    "beach": ["beach"],
    "viewpoint": ["viewpoint", "observation_deck"],
    "photography": ["viewpoint", "observation_deck", "historical_landmark", "tourist_attraction"],
}


def _tourist_type_score(types: list[str]) -> float:
    """
    Score based on Google place types.
    Returns the maximum TOURIST_TYPES weight found in the types list.
    Returns 0.0 if no tourist type is found.
    """
    if not types:
        return 0.0
    best = 0.0
    for t in types:
        score = TOURIST_TYPES.get(t, 0.0)
        if score > best:
            best = score
    return best


def _is_commercial(types: list[str]) -> bool:
    """True if the place is primarily a commercial business (no tourist value)."""
    for t in types:
        if t in COMMERCIAL_TYPES:
            # Allow if it ALSO has a tourist type
            if any(tt in TOURIST_TYPES for tt in types):
                return False
            return True
    return False


def _rating_score(rating: float | None, user_ratings_total: int | None) -> float:
    """
    Combined rating quality score.
    rating: 0–5 → normalized to 0–1
    user_ratings_total: log-normalized popularity signal
    Returns 0.5 (neutral) when data is unavailable.
    """
    if rating is None:
        return 0.5  # neutral — don't penalize missing data
    rating_norm = rating / 5.0

    # Popularity boost from review count (diminishing returns)
    if user_ratings_total and user_ratings_total > 0:
        pop_norm = min(1.0, math.log10(user_ratings_total + 1) / 4.0)  # 10k+ reviews → 1.0
    else:
        pop_norm = 0.3  # has a rating but no count → slight signal

    return 0.65 * rating_norm + 0.35 * pop_norm


def _preference_match(types: list[str], preferences: list[str]) -> float:
    """
    How well this place matches user memory preferences.
    Returns 0.0–1.0.
    """
    if not preferences or not types:
        return 0.5  # neutral

    types_set = set(types)
    match_count = 0
    total = len(preferences)

    for pref in preferences:
        pref_lower = pref.lower().strip()
        # Direct type match
        if pref_lower in types_set:
            match_count += 1
            continue
        # Keyword → type mapping
        mapped_types = _PREFERENCE_TYPE_MAP.get(pref_lower, [])
        if any(mt in types_set for mt in mapped_types):
            match_count += 1

    return match_count / total if total > 0 else 0.5


def _distance_score(distance_m: float, radius_m: int) -> float:
    """Linear distance score: 1.0 at centre, 0.0 at radius boundary."""
    if radius_m <= 0:
        return 0.5
    return max(0.0, 1.0 - (distance_m / radius_m))


def _intent_match(types: list[str], slot_intent: str) -> float:
    """
    How well place types match the planning intent string.
    e.g. slot_intent="temple visit" → hindu_temple → 1.0
    """
    intent_lower = slot_intent.lower()
    for keyword, mapped_types in _PREFERENCE_TYPE_MAP.items():
        if keyword in intent_lower:
            if any(mt in types for mt in mapped_types):
                return 1.0
    # Type name substring match
    for t in types:
        if any(word in t.lower() for word in intent_lower.split()):
            return 0.7
    return 0.0


class TouristRanker:
    """
    SCIF scoring component for ranking place candidates in attraction slots.

    Scores are deterministic and based only on verified data from the provider.
    No scores are fabricated when data is unavailable — missing data uses
    documented neutral values.
    """

    def score_candidates(
        self,
        candidates: list[PlaceCandidate],
        *,
        slot_intent: str = "",
        user_preferences: list[str] | None = None,
        radius_m: int = 5000,
        used_place_ids: set[str] | None = None,
    ) -> list[PlaceCandidate]:
        """
        Score and rank candidates for an attraction slot.

        Formula:
            score = 0.30 * tourist_type_score
                  + 0.25 * rating_score
                  + 0.20 * preference_match
                  + 0.15 * intent_match
                  + 0.10 * distance_score
                  - COMMERCIAL_PENALTY  (if purely commercial)
                  - DUPLICATE_PENALTY   (if already used)

        Sets candidate.tourist_relevance on each candidate.
        Returns candidates sorted by score descending.
        """
        prefs = user_preferences or []
        used = used_place_ids or set()

        scored = []
        for c in candidates:
            tourist_type = _tourist_type_score(c.types)
            rating = _rating_score(c.rating, c.user_ratings_total)
            pref = _preference_match(c.types, prefs)
            intent = _intent_match(c.types, slot_intent)
            dist = _distance_score(c.distance_m, radius_m)

            score = (
                0.30 * tourist_type
                + 0.25 * rating
                + 0.20 * pref
                + 0.15 * intent
                + 0.10 * dist
            )

            if _is_commercial(c.types):
                score -= COMMERCIAL_PENALTY
                logger.debug(
                    "tourist_ranker commercial_penalty place=%r types=%s score_before=%.2f",
                    c.name, c.types[:3], score + COMMERCIAL_PENALTY,
                )

            if c.place_id in used:
                score -= DUPLICATE_PENALTY

            c.tourist_relevance = max(0.0, score)
            scored.append(c)

        scored.sort(key=lambda x: x.tourist_relevance, reverse=True)

        logger.info(
            "tourist_ranker slot_intent=%r candidates=%d "
            "top=%r top_score=%.2f top_types=%s",
            slot_intent,
            len(candidates),
            scored[0].name if scored else "none",
            scored[0].tourist_relevance if scored else 0.0,
            scored[0].types[:3] if scored else [],
        )
        return scored

    def score_restaurant_candidates(
        self,
        candidates: list[PlaceCandidate],
        *,
        food_query: str = "",
        meal_type: str | None = None,
        user_preferences: list[str] | None = None,
        radius_m: int = 5000,
        used_place_ids: set[str] | None = None,
    ) -> list[PlaceCandidate]:
        """
        Score and rank restaurant candidates.

        Formula:
            score = 0.35 * rating_score
                  + 0.25 * cuisine_match
                  + 0.25 * meal_type_match
                  + 0.15 * distance_score
                  - DUPLICATE_PENALTY  (if already used)
        """
        from difflib import SequenceMatcher
        used = used_place_ids or set()

        def cuisine_match(name: str) -> float:
            if not food_query or not name:
                return 0.0
            return SequenceMatcher(None, name.lower(), food_query.lower()).ratio()

        def meal_match(types: list[str]) -> float:
            if not meal_type:
                return 0.5
            mt = meal_type.lower()
            if mt == "breakfast":
                return 1.0 if any(t in types for t in ["cafe", "bakery"]) else 0.4
            if mt == "lunch":
                return 1.0 if "restaurant" in types else 0.6
            if mt == "dinner":
                return 1.0 if "restaurant" in types else 0.5
            return 0.5

        scored = []
        for c in candidates:
            rating = _rating_score(c.rating, c.user_ratings_total)
            cu = cuisine_match(c.name)
            mm = meal_match(c.types)
            dist = _distance_score(c.distance_m, radius_m)

            score = (
                0.35 * rating
                + 0.25 * cu
                + 0.25 * mm
                + 0.15 * dist
            )
            if c.place_id in used:
                score -= DUPLICATE_PENALTY

            c.tourist_relevance = max(0.0, score)
            scored.append(c)

        scored.sort(key=lambda x: x.tourist_relevance, reverse=True)
        return scored


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_tourist_ranker: TouristRanker | None = None


def get_tourist_ranker() -> TouristRanker:
    global _tourist_ranker
    if _tourist_ranker is None:
        _tourist_ranker = TouristRanker()
    return _tourist_ranker
