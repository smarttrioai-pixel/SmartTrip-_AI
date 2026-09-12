"""
SCIF Planning Agents for SmartTrip AI.

Real agent interfaces that wrap existing cognitive engines and external APIs.
Each agent has a distinct data source and contributes to CognitivePlanningContext.

Agents (with data sources):
    MemoryAgent       → Firestore (memory_longterm)
    WeatherAgent      → Open-Meteo (via LiveContextEngine)
    NavigationAgent   → Geoapify geocoding (via NavigationService)
    BudgetAgent       → Internal calculation (no API)
    SafetyAgent       → Internal heuristic (RiskAssessmentEngine)

Orchestrator:
    SCIFOrchestrator  → Runs all agents, SCIF Pass 1, assembles CognitivePlanningContext

NOT IMPLEMENTED (no real API/data source exists in this project):
    HotelAgent        → No hotel availability API configured
    EventsAgent       → No local events API configured
    TrafficAgent      → No real-time traffic API (OSRM is static routing)
    CrowdAgent        → No crowd density API configured
"""

from app.agents.budget_agent import BudgetAgent
from app.agents.memory_agent import MemoryAgent
from app.agents.navigation_agent import NavigationAgent
from app.agents.safety_agent import SafetyAgent
from app.agents.scif_orchestrator import SCIFOrchestrator
from app.agents.weather_agent import WeatherAgent

__all__ = [
    "BudgetAgent",
    "MemoryAgent",
    "NavigationAgent",
    "SafetyAgent",
    "WeatherAgent",
    "SCIFOrchestrator",
]
