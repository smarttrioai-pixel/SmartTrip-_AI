"""
BudgetAgent for SmartTrip AI (SCIF Framework).

Performs real pre-Qwen budget analysis using only the user's input data.
No LLM calls. No external APIs. Pure deterministic calculation.

Data source: user request (budget, currency, num_days, travel_style)

Output: BudgetContext with daily breakdown and planning constraints
that are injected into SCIF Pass 1 and the Qwen prompt.

Design rules:
- Never fabricate exchange rates or destination cost-of-living data.
- Budget tiers are based on daily budget in the user's currency.
- Constraints are human-readable and actionable for Qwen.
- The tier label (budget/mid_range/luxury) is relative to the user's
  own stated budget, not an absolute USD threshold.
"""
from __future__ import annotations

import logging
import time

from app.cognitive.live_context import AgentOutput, BudgetContext

logger = logging.getLogger(__name__)


# Budget tier thresholds as a ratio of daily budget.
# These are relative, not absolute — so they work in any currency.
# The "budget" tier is anything below 30% of what a "luxury" trip would
# require. Since we don't know the destination's cost-of-living, we use
# the user's own budget as the only signal.
#
# We categorize based on daily budget (currency-agnostic):
#   < 30 units/day  → budget
#   30–150 units/day → mid_range
#   > 150 units/day → luxury
#
# This works reasonably in INR, USD, EUR, etc. and is transparent.
_BUDGET_TIER_LOW = 30.0     # e.g. <$30/day = budget
_BUDGET_TIER_HIGH = 150.0   # e.g. >$150/day = luxury

# Allocation ratios (must sum to 1.0)
_MEAL_RATIO = 0.25
_ACTIVITY_RATIO = 0.35
_TRANSPORT_RATIO = 0.20
_ACCOMMODATION_RATIO = 0.20


class BudgetAgent:
    """
    SCIF Planning Agent — Budget Analysis.

    Runs BEFORE Qwen. Produces structured budget constraints that
    prevent Qwen from recommending activities beyond the user's means.

    This agent does NOT call any external service or LLM.
    """

    async def analyze(
        self,
        total_budget: float,
        currency: str,
        num_days: int,
        travel_style: str = "balanced",
    ) -> tuple[BudgetContext, AgentOutput]:
        """
        Analyze the budget and produce BudgetContext + AgentOutput.

        Returns:
            (BudgetContext, AgentOutput) — both are populated from calculation only.
        """
        t0 = time.monotonic()

        num_days = max(1, num_days)
        daily = total_budget / num_days

        # Allocation breakdown
        meal_daily = daily * _MEAL_RATIO
        activity_daily = daily * _ACTIVITY_RATIO
        transport_daily = daily * _TRANSPORT_RATIO
        accommodation_daily = daily * _ACCOMMODATION_RATIO

        # Tier classification
        if daily < _BUDGET_TIER_LOW:
            tier = "budget"
        elif daily <= _BUDGET_TIER_HIGH:
            tier = "mid_range"
        else:
            tier = "luxury"

        # Build planning constraints
        constraints = self._build_constraints(
            daily=daily,
            meal_daily=meal_daily,
            activity_daily=activity_daily,
            currency=currency,
            tier=tier,
            travel_style=travel_style,
        )

        budget_ctx = BudgetContext(
            total_budget=total_budget,
            currency=currency,
            num_days=num_days,
            daily_budget=round(daily, 2),
            meal_budget_per_day=round(meal_daily, 2),
            activity_budget_per_day=round(activity_daily, 2),
            transport_budget_per_day=round(transport_daily, 2),
            accommodation_budget_per_day=round(accommodation_daily, 2),
            tier=tier,
            constraints=constraints,
            source="internal_calculation",
        )

        latency_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "BUDGET_AGENT budget=%.0f %s days=%d daily=%.1f tier=%s constraints=%d",
            total_budget, currency, num_days, daily, tier, len(constraints),
        )

        agent_output = AgentOutput(
            agent_name="BudgetAgent",
            status="ok",
            data_source="internal_calculation",
            contribution_summary=(
                f"{tier.replace('_', ' ').title()} trip: "
                f"{currency} {daily:.0f}/day "
                f"(meals {meal_daily:.0f}, activities {activity_daily:.0f})"
            ),
            items_returned=len(constraints),
            latency_ms=latency_ms,
            details={
                "tier": tier,
                "daily_budget": round(daily, 2),
                "currency": currency,
                "constraints_count": len(constraints),
            },
        )

        return budget_ctx, agent_output

    @staticmethod
    def _build_constraints(
        daily: float,
        meal_daily: float,
        activity_daily: float,
        currency: str,
        tier: str,
        travel_style: str,
    ) -> list[str]:
        """Build actionable planning constraints from budget analysis."""
        constraints: list[str] = []

        # Daily budget constraint
        constraints.append(
            f"Daily budget: {currency} {daily:.0f} per day. "
            f"Stay within this limit across meals, activities, and transport."
        )

        # Meal budget
        constraints.append(
            f"Meal budget: approximately {currency} {meal_daily:.0f} per day "
            f"({currency} {meal_daily/3:.0f} per meal). "
            f"Prefer local eateries within this range."
        )

        # Activity budget
        constraints.append(
            f"Activity budget: approximately {currency} {activity_daily:.0f} per day. "
            f"Prioritize free or low-cost attractions where possible."
        )

        # Tier-specific constraints
        if tier == "budget":
            constraints.append(
                "BUDGET TIER: Prioritize free attractions, street food, and budget restaurants. "
                "Avoid premium/luxury venues. Prefer walking over paid transport where feasible."
            )
        elif tier == "mid_range":
            constraints.append(
                "MID-RANGE TIER: Mix of free and paid attractions is appropriate. "
                "Mid-range restaurants are suitable. One premium experience per day is acceptable."
            )
        else:  # luxury
            constraints.append(
                "LUXURY TIER: Premium experiences, fine dining, and upscale venues are appropriate. "
                "Comfort and quality take priority over cost minimization."
            )

        # Travel style modifier
        if travel_style == "budget":
            constraints.append(
                "Travel style is budget-focused: maximize value, minimize costs."
            )
        elif travel_style == "luxury":
            constraints.append(
                "Travel style is luxury: quality and comfort are the priority."
            )

        return constraints
