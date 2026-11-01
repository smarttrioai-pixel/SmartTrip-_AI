"""
Deterministic itinerary validation for SmartTrip AI.

LLM output is treated as a plan proposal, not as ground truth. This module
removes unsupported transport assumptions and normalizes activity ordering.
No destination-specific rules are used.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any


# Matches "HH:MM AM/PM", "HH:MM", "HHAM/PM" (with or without space before meridiem).
_TIME_RE = re.compile(
    r"^\s*(\d{1,2})(?::(\d{2}))?\s*([AaPp][Mm])?\s*$"
)


def _time_key(value: str) -> int:
    """
    Parse a time string and return minutes-since-midnight as a sort key.

    Handles:
      - 12-hour AM/PM  e.g. "10:00 AM", "02:00 PM", "12:00 AM", "12:00 PM"
      - 24-hour        e.g. "09:00", "14:30"
      - Missing / invalid -> 24*60+1 (sorts AFTER all valid times)

    Special cases (standard clock rules):
      12:00 AM  -> 0 min    (midnight, start of day)
      12:00 PM  -> 720 min  (noon)
    """
    match = _TIME_RE.match(value or "")
    if not match:
        return 24 * 60 + 1  # unscheduled — sort last

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or "").lower()

    if meridiem:
        if not 1 <= hour <= 12:
            return 24 * 60 + 1  # invalid hour for 12-hr clock
        if meridiem == "pm" and hour != 12:
            hour += 12   # 01 PM–11 PM → 13–23
        if meridiem == "am" and hour == 12:
            hour = 0     # 12 AM → midnight → 0
    else:
        # 24-hour format
        if hour > 23:
            return 24 * 60 + 1  # invalid

    return hour * 60 + minute


def sort_activities_in_days(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Sort activities within each day by ascending chronological start time.

    Rules:
    - Handles 12-hour (AM/PM) and 24-hour time strings correctly.
    - 12:00 AM  → 0   (midnight)
    - 12:00 PM  → 720 (noon)
    - Missing / unparseable times → placed AFTER all scheduled activities.
    - Activities are sorted per-day; activities are NEVER moved between days.
    - All activity fields (title, description, cost, category, id, metadata)
      are fully preserved — only order within the day's list changes.

    Idempotent: calling multiple times always produces the same result.
    """
    for day in days:
        activities = day.get("activities")
        if not isinstance(activities, list):
            continue
        day["activities"] = sorted(
            activities,
            key=lambda a: _time_key(str(a.get("time") or "")),
        )
    return days


def _is_airport_transfer(activity: dict[str, Any]) -> bool:
    text = " ".join(
        str(activity.get(key) or "").lower()
        for key in ("title", "description", "location", "category")
    )
    return (
        "airport" in text
        or "flight" in text
        or "air transfer" in text
        or "air travel" in text
    )


def validate_transport(days: list[dict[str, Any]], transport: str) -> list[dict[str, Any]]:
    """
    Remove airport/flight transfer activities unless air travel was explicitly
    selected. With transport='any', no arrival mode is inferred.
    """
    mode = (transport or "any").strip().lower()
    if mode == "flight":
        return days

    for day in days:
        activities = day.get("activities") or []
        day["activities"] = [
            activity for activity in activities
            if not _is_airport_transfer(activity)
        ]
    return days


def normalize_days(days: list[dict[str, Any]], transport: str) -> list[dict[str, Any]]:
    """
    Validate and normalize a list of day-plan dicts from the LLM.

    Steps:
    1. Drop any day that is not a dict.
    2. Deep-copy activities so downstream mutations don't affect the input.
    3. Sort activities within each day by chronological start time.
    4. Remove airport/flight activities when the user didn't select air travel.
    """
    cleaned: list[dict[str, Any]] = []
    for day in days:
        if not isinstance(day, dict):
            continue
        activities = [
            dict(a) for a in (day.get("activities") or [])
            if isinstance(a, dict)
        ]
        day["activities"] = activities
        cleaned.append(day)

    # Sort every day's activities by chronological start time.
    sort_activities_in_days(cleaned)
    return validate_transport(cleaned, transport)
