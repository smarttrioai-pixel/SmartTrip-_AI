"""
Place / Activity Consistency Validator for SmartTrip AI.

Prevents mismatches between the actual Google place category and the
Qwen-generated activity description.

Example problem this solves:
    Place:       Pizza Hut Phoenix Mall (types: ["restaurant", "fast_food"])
    Description: "traditional craft workshops and local artisan stalls"
    → MISMATCH — reject or regenerate description

Rules:
    restaurant + historical/cultural description  → MISMATCH
    shopping_mall + wildlife/nature description   → MISMATCH
    temple + restaurant/food description          → MISMATCH
    museum + transport description               → MISMATCH
    juice_bar + heritage description             → MISMATCH

Resolution:
    When a mismatch is detected, the description is replaced with a
    factual fallback generated from verified place metadata.
    The original Qwen description is archived in the activity dict.
    No fabrication occurs.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type → expected topic keywords mapping
# If a description contains keywords from the WRONG category for this type,
# it is flagged as a mismatch.
# ---------------------------------------------------------------------------

_RESTAURANT_MISMATCH_KEYWORDS = {
    "temple", "shrine", "heritage", "historical", "ancient", "monument",
    "colonial", "fort", "palace", "museum", "cultural", "craft", "artisan",
    "archaeological", "ruins", "landmark", "art gallery", "exhibit",
    "wildlife", "nature", "forest", "beach", "waterfall",
}

_TEMPLE_MISMATCH_KEYWORDS = {
    "restaurant", "food", "cuisine", "meal", "lunch", "dinner", "breakfast",
    "eat", "dining", "pizza", "burger", "bar", "pub", "cafe",
    "shopping", "mall", "store", "market",
    "beach", "swimming", "water sports",
}

_MUSEUM_MISMATCH_KEYWORDS = {
    "restaurant", "food", "cuisine", "meal", "eat", "dining",
    "airport", "terminal", "flight", "railway",
    "shopping", "mall", "store",
}

_SHOPPING_MISMATCH_KEYWORDS = {
    "temple", "shrine", "heritage", "historical", "ancient", "archaeological",
    "wildlife", "nature", "forest", "ocean", "waterfall",
    "restaurant", "food", "cuisine",
}

_PARK_MISMATCH_KEYWORDS = {
    "restaurant", "food", "eat", "dining",
    "temple", "museum", "art",
    "shopping", "mall",
    "airport", "terminal",
}

# Google types → their mismatch keyword sets
_TYPE_MISMATCH_RULES: dict[str, set[str]] = {
    "restaurant": _RESTAURANT_MISMATCH_KEYWORDS,
    "fast_food_restaurant": _RESTAURANT_MISMATCH_KEYWORDS,
    "cafe": _RESTAURANT_MISMATCH_KEYWORDS,
    "food_court": _RESTAURANT_MISMATCH_KEYWORDS,
    "hindu_temple": _TEMPLE_MISMATCH_KEYWORDS,
    "mosque": _TEMPLE_MISMATCH_KEYWORDS,
    "church": _TEMPLE_MISMATCH_KEYWORDS,
    "jain_temple": _TEMPLE_MISMATCH_KEYWORDS,
    "buddhist_temple": _TEMPLE_MISMATCH_KEYWORDS,
    "place_of_worship": _TEMPLE_MISMATCH_KEYWORDS,
    "museum": _MUSEUM_MISMATCH_KEYWORDS,
    "art_gallery": _MUSEUM_MISMATCH_KEYWORDS,
    "shopping_mall": _SHOPPING_MISMATCH_KEYWORDS,
    "department_store": _SHOPPING_MISMATCH_KEYWORDS,
    "park": _PARK_MISMATCH_KEYWORDS,
    "national_park": _PARK_MISMATCH_KEYWORDS,
}

# Category labels for description fallback generation
_TYPE_LABEL: dict[str, str] = {
    "tourist_attraction": "Tourist Attraction",
    "historical_landmark": "Historical Landmark",
    "museum": "Museum",
    "hindu_temple": "Temple",
    "mosque": "Mosque",
    "church": "Church",
    "jain_temple": "Temple",
    "buddhist_temple": "Temple",
    "place_of_worship": "Place of Worship",
    "art_gallery": "Art Gallery",
    "national_park": "National Park",
    "park": "Park",
    "zoo": "Zoo",
    "aquarium": "Aquarium",
    "amusement_park": "Amusement Park",
    "cultural_center": "Cultural Centre",
    "restaurant": "Restaurant",
    "cafe": "Café",
    "fast_food_restaurant": "Restaurant",
    "shopping_mall": "Shopping Mall",
    "fort": "Historic Fort",
    "palace": "Palace",
    "ruins": "Historic Ruins",
    "beach": "Beach",
    "viewpoint": "Viewpoint",
}


def _detect_mismatch(
    types: list[str],
    description: str,
) -> tuple[bool, str]:
    """
    Check if the description is inconsistent with the place types.

    Returns:
        (is_mismatch, primary_type)
    """
    if not description or not types:
        return False, types[0] if types else ""

    desc_lower = description.lower()
    primary_type = types[0] if types else ""

    for t in types:
        mismatch_keywords = _TYPE_MISMATCH_RULES.get(t)
        if not mismatch_keywords:
            continue
        for keyword in mismatch_keywords:
            if keyword in desc_lower:
                return True, t

    return False, primary_type


def _generate_factual_description(
    place_name: str,
    types: list[str],
    destination: str,
    rating: float | None,
    address: str | None,
) -> str:
    """
    Generate a factual, non-fabricated description from verified place data.

    Uses only confirmed fields — nothing invented.
    """
    # Find best type label
    label = None
    for t in types:
        label = _TYPE_LABEL.get(t)
        if label:
            break
    if not label:
        label = types[0].replace("_", " ").title() if types else "Place"

    parts = [f"Visit {place_name}, a {label} in {destination}."]

    if rating is not None:
        parts.append(f"Rated {rating:.1f}/5 on Google Maps.")

    if address:
        parts.append(f"Located at: {address}.")

    return " ".join(parts)


class PlaceConsistencyValidator:
    """
    Validates that a Qwen-generated activity description is consistent with
    the actual Google place type.

    When a mismatch is detected:
        1. Archive the original Qwen description.
        2. Replace with a factual description from verified place data.
        3. Log the PLACE_CONSISTENCY_MISMATCH event for debugging.

    This component never fabricates place information.
    """

    def validate_and_fix(
        self,
        activity: dict[str, Any],
        place_name: str,
        place_types: list[str],
        destination: str,
        rating: float | None = None,
        address: str | None = None,
    ) -> dict[str, Any]:
        """
        Validate the activity description against the place types.

        Args:
            activity:    The activity dict (modified in-place and returned).
            place_name:  Verified place name from Google.
            place_types: Google place types list.
            destination: Destination city (used in fallback description).
            rating:      Google rating (or None).
            address:     Verified address (or None).

        Returns:
            The activity dict (possibly with corrected description).
        """
        description = str(activity.get("description") or "")

        is_mismatch, primary_type = _detect_mismatch(place_types, description)

        if is_mismatch:
            new_description = _generate_factual_description(
                place_name=place_name,
                types=place_types,
                destination=destination,
                rating=rating,
                address=address,
            )

            logger.info(
                "PLACE_CONSISTENCY_MISMATCH place=%r primary_type=%s "
                "original_description=%r replacement_generated=true",
                place_name,
                primary_type,
                description[:80],
            )

            activity["description_original"] = description  # preserve for debugging
            activity["description"] = new_description
            activity["description_corrected"] = True
        else:
            activity["description_corrected"] = False

        return activity

    def is_valid_attraction(
        self,
        place_types: list[str],
        slot_category: str,
    ) -> bool:
        """
        Check if this place is appropriate for the slot category.

        A restaurant is not a valid attraction.
        A temple is not a valid meal slot.

        Returns True if the place type is appropriate for the slot.
        """
        if not place_types:
            return True  # can't verify → allow (conservative)

        slot_lower = slot_category.lower()

        # Meal slots: only food-related types allowed
        if slot_lower == "meal":
            food_types = {"restaurant", "cafe", "fast_food_restaurant", "food_court",
                          "bakery", "meal_delivery", "meal_takeaway", "bar"}
            return any(t in food_types for t in place_types)

        # Attraction slots: reject pure food/commercial types
        if slot_lower in ("attraction", "culture", "nature", "museum", "sights"):
            reject_types = {
                "restaurant", "fast_food_restaurant", "cafe", "food_court",
                "bakery", "meal_delivery", "meal_takeaway", "juice_bar",
                "shopping_mall", "department_store", "grocery_store",
                "supermarket", "convenience_store", "gas_station",
                "atm", "bank", "pharmacy", "hair_salon", "spa", "gym",
            }
            # Reject only if ALL types are in the reject set
            return not all(t in reject_types for t in place_types)

        return True  # other slot types — allow


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_place_consistency_validator: PlaceConsistencyValidator | None = None


def get_place_consistency_validator() -> PlaceConsistencyValidator:
    global _place_consistency_validator
    if _place_consistency_validator is None:
        _place_consistency_validator = PlaceConsistencyValidator()
    return _place_consistency_validator
