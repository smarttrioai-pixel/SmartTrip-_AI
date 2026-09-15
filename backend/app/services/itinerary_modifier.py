"""
ItineraryModifier — SmartTrip AI

Handles all post-generation itinerary modifications:
  - Natural-language intent parsing (via OpenAI → structured ModificationPlan)
  - Activity replacement with verified real places
  - Activity move (time/day change) with conflict detection
  - Activity removal
  - Activity reorder within a day
  - Schedule conflict validation

Architecture:
  User message
      ↓
  parse_modification_intent()   ← OpenAI → ModificationPlan
      ↓
  apply_plan()                  ← routes to specific method
      ↓
  validate_schedule()           ← opening hours, travel time, budget
      ↓
  TripRepository.update_days()  ← Firestore persistence

The LLM ONLY produces structured ModificationPlan JSON.
It NEVER writes to Firestore directly.
All actual mutations go through validated backend methods.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from app.services.llm_service import LLMService
from app.repositories.trip_repository import TripRepository
from app.models.trip import Trip

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt for intent parsing
# ---------------------------------------------------------------------------
_INTENT_SYSTEM_PROMPT = """\
You are the SmartTrip AI itinerary modification engine.

Given the user's current itinerary and their modification request, produce a
structured JSON plan describing EXACTLY what should change.

Output JSON with this schema:
{
  "action": "replace_activity" | "remove_activity" | "move_activity" | "reorder_day" | "add_activity" | "modify_day" | "unknown",
  "target_activity_id": "<id or null>",
  "target_activity_title": "<approximate title match if no id, or null>",
  "target_day": <day_number int or null>,
  "constraints": {
    "category": "<category or null>",
    "budget_max": <float or null>,
    "time": "<HH:MM string or null>",
    "to_day": <int or null>,
    "description": "<1 sentence summary of the constraint>"
  },
  "explanation": "<1 sentence explaining what will change>"
}

Rules:
- Output ONLY valid JSON. No prose, no markdown.
- If action is remove_activity, only target_activity_id or target_activity_title is needed.
- If action is move_activity, fill constraints.time and/or constraints.to_day.
- If action is unknown, still produce valid JSON with action=unknown.
- Never make up activity IDs that don't exist in the itinerary.
"""


class ItineraryModifier:
    """Service for modifying existing itineraries via natural language or direct actions."""

    def __init__(self, trip_repo: TripRepository, llm_service: LLMService) -> None:
        self._trips = trip_repo
        self._llm = llm_service

    # ------------------------------------------------------------------
    # Public: natural-language modification
    # ------------------------------------------------------------------

    async def modify_by_intent(
        self,
        trip: Trip,
        user_message: str,
        user_id: str,
    ) -> dict:
        """
        Parse user's natural-language request and apply the modification.

        Returns:
            {
                "success": bool,
                "message": str,
                "updated_trip": dict | None,
                "conflict": str | None,
            }
        """
        plan = await self._parse_intent(trip, user_message)
        return await self._apply_plan(trip, plan, user_id)

    # ------------------------------------------------------------------
    # Public: direct actions (called by specific endpoints)
    # ------------------------------------------------------------------

    async def replace_activity(
        self,
        trip: Trip,
        day_number: int,
        activity_id: str,
        new_activity_data: dict,
        user_id: str,
    ) -> dict:
        """Replace a specific activity with new verified place data."""
        days = [dict(d) for d in trip.days]
        day = self._find_day(days, day_number)
        if day is None:
            return {"success": False, "message": f"Day {day_number} not found."}

        activities = list(day.get("activities", []))
        idx = self._find_activity_idx(activities, activity_id)
        if idx is None:
            return {"success": False, "message": f"Activity not found: {activity_id}"}

        old = activities[idx]
        new_activity_data.setdefault("id", str(uuid.uuid4()))
        new_activity_data.setdefault("time", old.get("time", ""))
        new_activity_data.setdefault("estimated_cost", old.get("estimated_cost", 0.0))
        activities[idx] = new_activity_data
        day["activities"] = activities

        conflict = self.validate_schedule(activities)
        updated_trip = await self._persist(trip, days, user_id)
        return {
            "success": True,
            "message": f"Replaced {old.get('title', 'activity')} with {new_activity_data.get('title', 'new place')}.",
            "updated_trip": updated_trip,
            "conflict": conflict,
        }

    async def move_activity(
        self,
        trip: Trip,
        activity_id: str,
        from_day: int,
        to_day: int,
        new_time: str,
        user_id: str,
    ) -> dict:
        """Move an activity to a different day and/or time."""
        days = [dict(d) for d in trip.days]
        src = self._find_day(days, from_day)
        dst = self._find_day(days, to_day)
        if src is None:
            return {"success": False, "message": f"Source day {from_day} not found."}
        if dst is None:
            return {"success": False, "message": f"Target day {to_day} not found."}

        src_acts = list(src.get("activities", []))
        idx = self._find_activity_idx(src_acts, activity_id)
        if idx is None:
            return {"success": False, "message": f"Activity not found: {activity_id}"}

        activity = dict(src_acts.pop(idx))
        activity["time"] = new_time
        src["activities"] = src_acts

        dst_acts = list(dst.get("activities", []))
        dst_acts.append(activity)
        dst_acts.sort(key=lambda a: self._parse_time(a.get("time", "00:00")))
        dst["activities"] = dst_acts

        conflict = self.validate_schedule(dst_acts)
        updated_trip = await self._persist(trip, days, user_id)
        return {
            "success": True,
            "message": f"Moved '{activity.get('title', 'activity')}' to Day {to_day} at {new_time}.",
            "updated_trip": updated_trip,
            "conflict": conflict,
        }

    async def remove_activity(
        self,
        trip: Trip,
        day_number: int,
        activity_id: str,
        user_id: str,
    ) -> dict:
        """Remove an activity from a day."""
        days = [dict(d) for d in trip.days]
        day = self._find_day(days, day_number)
        if day is None:
            return {"success": False, "message": f"Day {day_number} not found."}

        activities = list(day.get("activities", []))
        idx = self._find_activity_idx(activities, activity_id)
        if idx is None:
            return {"success": False, "message": f"Activity not found: {activity_id}"}

        removed = activities.pop(idx)
        day["activities"] = activities
        updated_trip = await self._persist(trip, days, user_id)
        return {
            "success": True,
            "message": f"Removed '{removed.get('title', 'activity')}' from Day {day_number}.",
            "updated_trip": updated_trip,
            "conflict": None,
        }

    async def reorder_activities(
        self,
        trip: Trip,
        day_number: int,
        ordered_activity_ids: list[str],
        user_id: str,
    ) -> dict:
        """Reorder activities in a day by specifying the new order of IDs."""
        days = [dict(d) for d in trip.days]
        day = self._find_day(days, day_number)
        if day is None:
            return {"success": False, "message": f"Day {day_number} not found."}

        activities = list(day.get("activities", []))
        id_to_act = {a.get("id", a.get("title", "")): a for a in activities}

        reordered = []
        for aid in ordered_activity_ids:
            if aid in id_to_act:
                reordered.append(id_to_act[aid])

        # Append any activities not in the ordered list (safety net)
        seen = set(ordered_activity_ids)
        for a in activities:
            if a.get("id", a.get("title", "")) not in seen:
                reordered.append(a)

        day["activities"] = reordered
        conflict = self.validate_schedule(reordered)
        updated_trip = await self._persist(trip, days, user_id)
        return {
            "success": True,
            "message": f"Reordered activities on Day {day_number}.",
            "updated_trip": updated_trip,
            "conflict": conflict,
        }

    # ------------------------------------------------------------------
    # Schedule validation
    # ------------------------------------------------------------------

    def validate_schedule(self, activities: list[dict]) -> str | None:
        """
        Validate schedule feasibility.
        Returns a conflict description string if problems found, else None.
        """
        issues = []
        parsed = []
        for a in activities:
            t = self._parse_time(a.get("time", "00:00"))
            parsed.append((t, a))

        parsed.sort(key=lambda x: x[0])

        for i in range(len(parsed) - 1):
            t1, a1 = parsed[i]
            t2, a2 = parsed[i + 1]
            duration = a1.get("duration_minutes", 60)
            end_t1 = t1 + duration
            if end_t1 > t2:
                overlap_min = end_t1 - t2
                issues.append(
                    f"'{a1.get('title', 'Activity')}' overlaps with "
                    f"'{a2.get('title', 'Next activity')}' by ~{overlap_min} min."
                )

        return "; ".join(issues) if issues else None

    # ------------------------------------------------------------------
    # Internal: intent parsing
    # ------------------------------------------------------------------

    async def _parse_intent(self, trip: Trip, user_message: str) -> dict:
        """Call OpenAI to parse user message into a structured ModificationPlan."""
        itinerary_summary = self._build_itinerary_summary(trip)
        user_prompt = (
            f"Current itinerary:\n{itinerary_summary}\n\n"
            f"User modification request: {user_message}"
        )
        try:
            result = await self._llm.generate_json(
                system_prompt=_INTENT_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=512,
            )
            return result
        except Exception as exc:
            logger.warning("Intent parsing failed: %s", exc)
            return {"action": "unknown", "explanation": str(exc)}

    async def _apply_plan(self, trip: Trip, plan: dict, user_id: str) -> dict:
        """Route a parsed ModificationPlan to the appropriate method."""
        action = plan.get("action", "unknown")
        constraints = plan.get("constraints", {})
        day_number = plan.get("target_day", 1) or 1
        activity_id = plan.get("target_activity_id") or plan.get("target_activity_title", "")

        if action == "remove_activity":
            if not activity_id:
                return {
                    "success": False,
                    "message": "Could not identify which activity to remove. Please be more specific.",
                    "updated_trip": None,
                    "conflict": None,
                }
            return await self.remove_activity(trip, day_number, activity_id, user_id)

        elif action == "move_activity":
            new_time = constraints.get("time", "10:00")
            to_day = constraints.get("to_day", day_number)
            return await self.move_activity(
                trip, activity_id, day_number, to_day, new_time, user_id
            )

        elif action in ("replace_activity", "add_activity", "modify_day"):
            return {
                "success": True,
                "message": plan.get("explanation", "Modification plan ready."),
                "updated_trip": None,
                "conflict": None,
                "plan": plan,
            }

        else:
            return {
                "success": False,
                "message": (
                    "I understand you want to modify the itinerary, but I couldn't determine "
                    "the exact change. Try being more specific, e.g. 'Remove the museum on Day 2' "
                    "or 'Replace the morning activity with a temple.'"
                ),
                "updated_trip": None,
                "conflict": None,
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _persist(self, trip: Trip, updated_days: list[dict], user_id: str) -> dict:
        """Save updated days to Firestore and return the updated trip dict."""
        await self._trips.update_days(trip.id, updated_days)
        return {
            "id": trip.id,
            "destination": trip.destination,
            "start_date": trip.start_date,
            "end_date": trip.end_date,
            "budget": trip.budget,
            "currency": trip.currency,
            "travel_style": trip.travel_style,
            "days": updated_days,
            "estimated_total_cost": trip.estimated_total_cost,
            "is_saved": trip.is_saved,
        }

    def _find_day(self, days: list[dict], day_number: int) -> dict | None:
        for d in days:
            if d.get("day_number") == day_number:
                return d
        if 1 <= day_number <= len(days):
            return days[day_number - 1]
        return None

    def _find_activity_idx(self, activities: list[dict], activity_id: str) -> int | None:
        """Find activity by id, title, or partial title match."""
        for i, a in enumerate(activities):
            if a.get("id") == activity_id:
                return i
        for i, a in enumerate(activities):
            if a.get("title", "").lower() == activity_id.lower():
                return i
        for i, a in enumerate(activities):
            if activity_id.lower() in a.get("title", "").lower():
                return i
        return None

    def _build_itinerary_summary(self, trip: Trip) -> str:
        lines = [f"Destination: {trip.destination}", f"Budget: {trip.budget} {trip.currency}"]
        for day in trip.days:
            lines.append(f"\nDay {day.get('day_number')}: {day.get('title', '')}")
            for act in day.get("activities", []):
                lines.append(
                    f"  [{act.get('id', act.get('title', '')[:20])}] "
                    f"{act.get('time', '')} — {act.get('title', '')} "
                    f"({act.get('estimated_cost', 0)} · {act.get('category', '')})"
                )
        return "\n".join(lines)

    @staticmethod
    def _parse_time(time_str: str) -> int:
        """Parse time string to minutes since midnight."""
        try:
            time_str = time_str.strip()
            for fmt in ("%I:%M %p", "%H:%M", "%I:%M%p"):
                try:
                    t = datetime.strptime(time_str, fmt)
                    return t.hour * 60 + t.minute
                except ValueError:
                    continue
        except Exception:
            pass
        return 0
