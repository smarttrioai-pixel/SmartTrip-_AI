"""
LangGraph Multi-Agent System Shared State for SmartTrip AI.
Defines the unified state graph passed across all 12 autonomous agents.
"""
from __future__ import annotations

from typing import Any, TypedDict, Annotated, List
import operator

class SmartTripState(TypedDict, total=False):
    user_id: str
    destination: str
    start_date: str
    end_date: str
    budget: float
    currency: str
    travel_style: str
    interests: List[str]
    current_request: str
    
    # Domain Agent Outputs
    raw_plan: dict[str, Any]
    weather_info: dict[str, Any]
    safety_info: dict[str, Any]
    hotel_recommendations: list[dict[str, Any]]
    restaurant_recommendations: list[dict[str, Any]]
    navigation_route: dict[str, Any]
    budget_breakdown: dict[str, Any]
    vision_analysis: dict[str, Any]
    audio_narrations: list[dict[str, Any]]
    expenses: list[dict[str, Any]]
    diary_entry: dict[str, Any]
    analytics_report: dict[str, Any]

    # Shared Memory & System Metadata
    messages: Annotated[List[dict[str, str]], operator.add]
    execution_trace: Annotated[List[str], operator.add]
    errors: Annotated[List[str], operator.add]
    final_response: str
