"""
Tests for activity schema normalization and itinerary generation robustness.

These tests validate the normalization logic that maps Qwen's new intent
schema (slot_intent, reason, place_query) to the required Activity schema
fields (title, description, location).

Import strategy:
    - The normalization logic is tested via a local copy of the function to
      avoid importing the full planning_engine module chain (which depends on
      Firebase and other heavy deps that may not be present in CI/local).
    - Pydantic Activity/TripResponse are imported from app.schemas.trip which
      has no heavy dependencies.
    - The regression test for the exact Render error is included.

Covers:
  1.  slot_intent → title
  2.  reason → description
  3.  place_query → location, destination fallback → location
  4.  Old Qwen schema (title/description/location) untouched
  5.  Transport activity (no enrichment) → all required fields
  6.  Completely empty activity → safe defaults
  7.  Activity Pydantic: new Qwen schema → validates after normalization
  8.  Activity Pydantic: old schema → validates unchanged
  9.  Google Places 0 results → activity still valid
  10. Three-day itinerary, all activities valid (0 enrichment)
  11. Enriched activity: title from Google, description from reason
  12. Meal activity: valid after enrichment
  13. TripResponse: valid for 3-day itinerary (18 activities)
  14. TripResponse: multiple activities per day all valid
  15. Stage 7b sweep: post-enrichment description gap is fixed
  16. REGRESSION: exact Render error structure → normalized → valid
"""
from __future__ import annotations

import logging
import pytest

from app.schemas.trip import Activity, DayPlanResponse, TripResponse


logger = logging.getLogger(__name__)

DESTINATION = "Rajahmundry"


# ---------------------------------------------------------------------------
# Local copy of _normalize_pre_enrichment to avoid Firebase import chain.
# This is identical to the function in app.cognitive.planning_engine.
# ---------------------------------------------------------------------------

def _normalize_pre_enrichment(activity: dict, destination: str) -> None:
    """
    Map Qwen's new intent-schema fields onto the required Activity schema
    fields (title, description, location).
    """
    # ---- title ----
    if not activity.get("title"):
        title_candidate = (
            str(activity.get("slot_intent") or "")
            or str(activity.get("place_query") or "")
            or str(activity.get("category") or "Activity").replace("_", " ").title()
        )
        activity["title"] = title_candidate.strip() or "Activity"

    # ---- description ----
    if not activity.get("description"):
        description_candidate = (
            str(activity.get("reason") or "")
            or str(activity.get("slot_intent") or "")
            or str(activity.get("title") or "")
        )
        activity["description"] = description_candidate.strip() or "Part of your itinerary."

    # ---- location ----
    if not activity.get("location"):
        location_candidate = (
            str(activity.get("place_query") or "")
            or destination
        )
        activity["location"] = location_candidate.strip() or destination


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_activity(**kwargs) -> dict:
    """Minimal activity dict from Qwen new intent schema."""
    base = {
        "time": "09:00 AM",
        "slot_intent": "ancient temple visit",
        "place_query": "temples Rajahmundry",
        "place_type_hint": "hindu_temple",
        "category": "attraction",
        "meal_type": None,
        "food_query": None,
        "estimated_cost": 0.0,
        "preferred_duration_minutes": 90,
        "reason": "Explore the historical religious architecture of the region.",
    }
    base.update(kwargs)
    return base


def _make_activity_model(**kwargs) -> Activity:
    """Build a valid Activity model for TripResponse tests."""
    defaults = {
        "time": "09:00 AM",
        "title": "Kotilingeshwara Temple",
        "description": "Visit the ancient Shiva temple on the banks of the Godavari.",
        "location": "Kotilingeshwara Temple, Rajahmundry",
        "estimated_cost": 0.0,
        "category": "attraction",
    }
    defaults.update(kwargs)
    return Activity(**defaults)


# ---------------------------------------------------------------------------
# 1. slot_intent → title
# ---------------------------------------------------------------------------

def test_normalize_title_from_slot_intent():
    act = _base_activity()  # no title key
    _normalize_pre_enrichment(act, DESTINATION)
    assert act["title"] == "ancient temple visit"


# ---------------------------------------------------------------------------
# 2. reason → description
# ---------------------------------------------------------------------------

def test_normalize_description_from_reason():
    act = _base_activity()
    _normalize_pre_enrichment(act, DESTINATION)
    assert act["description"] == "Explore the historical religious architecture of the region."


# ---------------------------------------------------------------------------
# 3. place_query → location, destination fallback → location
# ---------------------------------------------------------------------------

def test_normalize_location_from_place_query():
    act = _base_activity()  # no location key
    _normalize_pre_enrichment(act, DESTINATION)
    assert act["location"] == "temples Rajahmundry"  # uses place_query first


def test_normalize_location_from_destination_no_place_query():
    act = _base_activity()
    del act["place_query"]
    _normalize_pre_enrichment(act, DESTINATION)
    assert act["location"] == DESTINATION


# ---------------------------------------------------------------------------
# 4. Old Qwen schema (title/description/location) → untouched
# ---------------------------------------------------------------------------

def test_normalize_old_schema_untouched():
    """If Qwen already outputs title/description/location, don't overwrite."""
    act = {
        "time": "10:00 AM",
        "title": "Old Title",
        "description": "Old description.",
        "location": "Old Location",
        "estimated_cost": 0.0,
        "category": "attraction",
    }
    _normalize_pre_enrichment(act, DESTINATION)
    assert act["title"] == "Old Title"
    assert act["description"] == "Old description."
    assert act["location"] == "Old Location"


# ---------------------------------------------------------------------------
# 5. Transport activity (no enrichment) → all required fields
# ---------------------------------------------------------------------------

def test_normalize_transport_activity():
    act = {
        "time": "08:00 AM",
        "slot_intent": "Arrive at destination",
        "category": "transport",
        "reason": "Travel from home city to the destination.",
        "estimated_cost": 0.0,
    }
    _normalize_pre_enrichment(act, DESTINATION)
    assert act["title"] == "Arrive at destination"
    assert "Travel" in act["description"]
    assert act["location"] == DESTINATION  # no place_query → destination


# ---------------------------------------------------------------------------
# 6. Completely empty activity → safe defaults
# ---------------------------------------------------------------------------

def test_normalize_empty_activity_safe_defaults():
    act = {"time": "09:00 AM", "estimated_cost": 0.0}
    _normalize_pre_enrichment(act, DESTINATION)
    assert act["title"]  # not empty
    assert act["description"]  # not empty
    assert act["location"] == DESTINATION


# ---------------------------------------------------------------------------
# 7. Activity Pydantic: new Qwen schema activity validates after normalization
# ---------------------------------------------------------------------------

def test_activity_pydantic_validates_after_normalization():
    act = _base_activity()
    _normalize_pre_enrichment(act, DESTINATION)
    # Filter to fields Activity accepts
    valid_keys = set(Activity.model_fields.keys())
    model = Activity(**{k: v for k, v in act.items() if k in valid_keys})
    assert model.title == "ancient temple visit"
    assert model.description != ""
    assert model.location != ""


# ---------------------------------------------------------------------------
# 8. Activity Pydantic: old schema validates unchanged
# ---------------------------------------------------------------------------

def test_activity_pydantic_old_schema_validates():
    model = Activity(
        time="09:00 AM",
        title="Godavari River Ghats",
        description="Walk along the famous ghats on the Godavari River.",
        location="Godavari Ghats, Rajahmundry",
        estimated_cost=0.0,
        category="attraction",
    )
    assert model.title == "Godavari River Ghats"
    assert model.description != ""
    assert model.location != ""


# ---------------------------------------------------------------------------
# 9. Google Places 0 results → activity still valid
# ---------------------------------------------------------------------------

def test_google_zero_results_activity_still_valid():
    """
    Simulates what happens when Google Places returns 0 results.
    Pre-enrichment normalization must have already set all required fields.
    """
    act = _base_activity()
    # Stage 6b: pre-enrichment normalization
    _normalize_pre_enrichment(act, DESTINATION)

    # Stage 7: enrichment returns None (0 results from Google)
    act["place_enrichment"] = {"found": False, "source": "google", "reason": "no_tourist_relevant_candidate"}

    # Stage 7b sweep — should not need to fix anything
    assert act["title"]
    assert act["description"]
    assert act["location"]

    # Must be valid Activity
    model = Activity(
        time=act["time"],
        title=act["title"],
        description=act["description"],
        location=act["location"],
        estimated_cost=act.get("estimated_cost", 0.0),
        category=act.get("category"),
        place_enrichment=act.get("place_enrichment"),
    )
    assert model.title != ""
    assert model.description != ""
    assert model.location != ""


# ---------------------------------------------------------------------------
# 10. Three days, all activities valid even when Google returns 0 results
# ---------------------------------------------------------------------------

def test_three_day_itinerary_all_activities_valid():
    days = [
        {
            "day_number": i + 1,
            "title": f"Day {i + 1}",
            "activities": [_base_activity(
                time=f"0{9+j}:00 AM" if j < 4 else f"0{j-3}:00 PM",
                slot_intent=f"attraction {j}",
                reason=f"Reason for activity {j}.",
            ) for j in range(6)]
        }
        for i in range(3)
    ]

    # Apply normalization and simulate 0 enrichment results
    for day in days:
        for act in day["activities"]:
            _normalize_pre_enrichment(act, DESTINATION)
            act["place_enrichment"] = {"found": False}

    # All activities must be valid Activity models
    for day in days:
        for act in day["activities"]:
            model = Activity(
                time=act["time"],
                title=act["title"],
                description=act["description"],
                location=act["location"],
                estimated_cost=act.get("estimated_cost", 0.0),
            )
            assert model.title
            assert model.description
            assert model.location


# ---------------------------------------------------------------------------
# 11. Enriched activity: title from Google place name, description from reason
# ---------------------------------------------------------------------------

def test_enriched_activity_title_from_google_description_from_reason():
    act = _base_activity()
    _normalize_pre_enrichment(act, DESTINATION)

    # Simulate Stage 7 enrichment success
    enriched = {
        "matched_place_name": "ISKCON Temple Rajahmundry",
        "address": "ISKCON Temple Road, Rajahmundry",
        "place_types": ["hindu_temple", "tourist_attraction"],
        "rating": 4.7,
        "source": "google",
    }
    act["title"] = enriched["matched_place_name"]
    act["location"] = enriched.get("address") or enriched["matched_place_name"]
    # description: keep existing reason
    if not act.get("description") or act.get("description") == act.get("slot_intent"):
        act["description"] = act.get("reason") or f"Visit {enriched['matched_place_name']} in {DESTINATION}."

    assert act["title"] == "ISKCON Temple Rajahmundry"
    assert act["location"] == "ISKCON Temple Road, Rajahmundry"
    # reason was set so description should be the reason
    assert "Explore" in act["description"]


# ---------------------------------------------------------------------------
# 12. Meal activity: valid after enrichment
# ---------------------------------------------------------------------------

def test_meal_activity_after_enrichment():
    act = {
        "time": "01:00 PM",
        "slot_intent": "Andhra lunch",
        "place_query": "Andhra meals restaurant Rajahmundry",
        "category": "meal",
        "meal_type": "lunch",
        "food_query": "Andhra meals",
        "estimated_cost": 10.0,
        "reason": "Sample authentic Andhra cuisine.",
    }
    _normalize_pre_enrichment(act, DESTINATION)

    # Simulate meal enrichment success
    act["title"] = "Lunch at Nagarjuna Restaurant"
    act["location"] = "Brodipet, Rajahmundry"
    if not act.get("description"):
        act["description"] = act.get("reason") or "Enjoy a meal."

    model = Activity(
        time=act["time"],
        title=act["title"],
        description=act["description"],
        location=act["location"],
        estimated_cost=act.get("estimated_cost", 0.0),
        category="meal",
        meal_type="lunch",
    )
    assert "Lunch at" in model.title
    assert model.description != ""
    assert model.location != ""


# ---------------------------------------------------------------------------
# 13. TripResponse: valid for 3-day itinerary (18 activities)
# ---------------------------------------------------------------------------

def test_trip_response_three_day_18_activities():
    activities = [
        _make_activity_model(
            time=f"0{9+i}:00 AM" if i < 4 else f"0{i-3}:00 PM",
            title=f"Place {i}",
            description=f"Description for place {i}.",
            location=f"Location {i}, {DESTINATION}",
        )
        for i in range(6)
    ]

    days = [
        DayPlanResponse(day_number=i + 1, title=f"Day {i + 1}", activities=activities)
        for i in range(3)
    ]

    response = TripResponse(
        id="trip_001",
        destination=DESTINATION,
        start_date="2026-09-01",
        end_date="2026-09-03",
        budget=10000.0,
        currency="INR",
        travel_style="balanced",
        days=days,
        estimated_total_cost=9000.0,
        is_saved=False,
    )

    assert len(response.days) == 3
    for day in response.days:
        assert len(day.activities) == 6
        for act in day.activities:
            assert act.title
            assert act.description
            assert act.location


# ---------------------------------------------------------------------------
# 14. TripResponse: multiple activities per day all valid
# ---------------------------------------------------------------------------

def test_trip_response_multiple_activities_per_day():
    day_activities = [
        _make_activity_model(
            time=f"0{8+i}:00 AM",
            title=f"Activity {i}",
            description=f"Do activity {i} in {DESTINATION}.",
            location=f"Spot {i}",
        )
        for i in range(8)
    ]

    response = TripResponse(
        id="trip_002",
        destination=DESTINATION,
        start_date="2026-10-01",
        end_date="2026-10-01",
        budget=5000.0,
        currency="INR",
        travel_style="active",
        days=[DayPlanResponse(day_number=1, title="Full Day", activities=day_activities)],
        estimated_total_cost=4500.0,
        is_saved=False,
    )

    assert len(response.days[0].activities) == 8
    for act in response.days[0].activities:
        assert act.title
        assert act.description
        assert act.location


# ---------------------------------------------------------------------------
# 15. Stage 7b sweep: post-enrichment gap is fixed by second normalize call
# ---------------------------------------------------------------------------

def test_stage7b_sweep_fixes_post_enrichment_gap():
    """
    Simulate an activity where enrichment set title and location but
    left description empty (edge case). Stage 7b sweep must fix it.
    """
    act = {
        "time": "03:00 PM",
        "title": "Pushkar Ghat",
        "description": "",       # ← gap after enrichment
        "location": "Pushkar Ghat, Rajahmundry",
        "estimated_cost": 0.0,
        "category": "attraction",
        "reason": "The sacred ghat on the Godavari river.",
        "slot_intent": "Godavari river ghat visit",
    }

    # Stage 7b check and fix
    if not act.get("title") or not act.get("description") or not act.get("location"):
        _normalize_pre_enrichment(act, DESTINATION)

    assert act["description"] != ""
    assert "sacred" in act["description"] or "Godavari" in act["description"]


# ---------------------------------------------------------------------------
# 16. REGRESSION: Exact Render error structure — normalized → valid
# ---------------------------------------------------------------------------

def test_regression_render_error_structure():
    """
    The exact structure from the Render error log:
    Activity dicts had 'slot_intent', 'place_query', 'reason', etc. but
    were missing 'title', 'description', 'location'.

    After normalization, these must all be valid Activity objects.
    """
    # Simulate the exact Render error activities
    failing_activities = [
        {
            "time": "09:00 AM",
            "slot_intent": "Visit historical ruins and ancient temples",
            "place_query": "historical temples ruins Kakinada",
            "place_type_hint": "hindu_temple",
            "category": "attraction",
            "meal_type": None,
            "food_query": None,
            "estimated_cost": 0.0,
            "preferred_duration_minutes": 90,
            "reason": "This area is rich in historical and cultural landmarks.",
        },
        {
            "time": "10:30 AM",
            "slot_intent": "Nature walk in botanical garden or park",
            "place_query": "botanical garden park Kakinada",
            "place_type_hint": "park",
            "category": "nature",
            "meal_type": None,
            "food_query": None,
            "estimated_cost": 0.0,
            "preferred_duration_minutes": 60,
            "reason": "Enjoy the natural beauty and greenery.",
        },
        {
            "time": "12:30 PM",
            "slot_intent": "Andhra meals lunch",
            "place_query": "Andhra meals restaurant Kakinada",
            "category": "meal",
            "meal_type": "lunch",
            "food_query": "Andhra tiffin meals Kakinada",
            "estimated_cost": 150.0,
            "reason": "Authentic Andhra cuisine for a hearty lunch.",
        },
        {
            "time": "02:30 PM",
            "slot_intent": "Beach visit",
            "place_query": "beaches Kakinada",
            "place_type_hint": "beach",
            "category": "nature",
            "meal_type": None,
            "food_query": None,
            "estimated_cost": 0.0,
            "preferred_duration_minutes": 120,
            "reason": "Relax at the coastal beaches.",
        },
    ]

    # Apply Stage 6b normalization
    for act in failing_activities:
        _normalize_pre_enrichment(act, "Kakinada")

    # ALL must pass Pydantic validation
    for i, act in enumerate(failing_activities):
        try:
            model = Activity(
                time=act["time"],
                title=act["title"],
                description=act["description"],
                location=act["location"],
                estimated_cost=act.get("estimated_cost", 0.0),
                category=act.get("category"),
                meal_type=act.get("meal_type"),
                food_query=act.get("food_query"),
            )
            assert model.title, f"Activity {i} has empty title"
            assert model.description, f"Activity {i} has empty description"
            assert model.location, f"Activity {i} has empty location"
        except Exception as exc:
            pytest.fail(f"Activity {i} failed validation: {exc}\nActivity: {act}")

    # Build a full day and validate as DayPlanResponse
    day = DayPlanResponse(
        day_number=1,
        title="Day 1 — Kakinada",
        activities=[
            Activity(
                time=act["time"],
                title=act["title"],
                description=act["description"],
                location=act["location"],
                estimated_cost=act.get("estimated_cost", 0.0),
                category=act.get("category"),
                meal_type=act.get("meal_type"),
            )
            for act in failing_activities
        ],
    )
    assert len(day.activities) == 4

    # Build full TripResponse
    response = TripResponse(
        id="regression_001",
        destination="Kakinada",
        start_date="2026-08-15",
        end_date="2026-08-17",
        budget=15000.0,
        currency="INR",
        travel_style="balanced",
        days=[day],
        estimated_total_cost=12000.0,
        is_saved=False,
    )
    assert response.id == "regression_001"
    assert len(response.days) == 1
    assert len(response.days[0].activities) == 4
