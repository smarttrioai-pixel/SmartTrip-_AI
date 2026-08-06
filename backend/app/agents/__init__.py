"""
Multi-agent orchestration package.

This package previously contained multi_agent_graph.py, a "12-agent"
system that did not use LangGraph despite its docstrings (plain
asyncio.gather()), and where every agent returned hardcoded fabricated
data — a Vision agent that always returned "Eiffel Tower" regardless of
input, a Weather/Navigation agent that always queried Paris coordinates
(48.8566, 2.3522), an Analytics agent with fixed fake percentages (94.2%),
a Planner agent that returned a static itinerary. It was also, critically,
briefly wired as the PRIMARY path for live trip generation before Phase 3A
removed that call — every itinerary generated in that window was the same
static template regardless of user input.

Confirmed via dependency analysis (see conversation/audit trail) that
nothing in production referenced this module after Phase 3A — the only
remaining reference was a test that exercised the fake module in
isolation, providing no real coverage. Removed entirely rather than kept
as dead weight.

Real multi-agent orchestration via LangGraph is a deliberate future
phase, not a resurrection of the removed file — see
Phase5_Multi_Agent_Layer_Design.md for the approved design: 9 real agents
(Planner, Budget, Safety, Weather, Hotel, Restaurant, Navigation,
Shopping, Tour Guide) each calling a real SCIF Cognitive Engine, real
Firestore repository, or a real Gemini/routing call — no static
dictionaries, no hardcoded coordinates, no fabricated metrics.
"""
