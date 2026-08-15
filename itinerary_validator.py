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


_TIME_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([AaPp][Mm])?\s*$")


def _time_key(value: str) -> int:
    match = _TIME_RE.match(value or "")
    if not match:
        return 24 * 60 + 1

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or "").lower()

    if meridiem:
        if not 1 <= hour <= 12:
            return 24 * 60 + 1
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
    elif hour > 23:
        return 24 * 60 + 1

    return hour * 60 + minute


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
    cleaned: list[dict[str, Any]] = []
    for day in days:
        if not isinstance(day, dict):
            continue
        activities = [
            dict(a) for a in (day.get("activities") or [])
            if isinstance(a, dict)
        ]
        day["activities"] = sorted(
            activities,
            key=lambda a: _time_key(str(a.get("time") or "")),
        )
        cleaned.append(day)

    return validate_transport(cleaned, transport)
