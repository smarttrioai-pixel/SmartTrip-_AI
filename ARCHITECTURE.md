# SmartTrip AI: System Architecture & Technical Specifications

> **System Paradigm**: Memory-Augmented Multimodal Agent Graph (SCIF Framework + LangGraph 12-Agent System)

---

## 🏛️ High-Level System Architecture

SmartTrip AI decouples business domain intelligence into three clean tiers:

```
+-----------------------------------------------------------------------+
|                         Next.js 14 Frontend                           |
|  Dashboard | Planner | MapLibre Nav | AR Explore | Diary | Analytics  |
+-----------------------------------------------------------------------+
                                   | HTTP / REST API & Streaming
+-----------------------------------------------------------------------+
|                           FastAPI Router                              |
|   /profile  /trips  /chat  /memory  /navigation  /explore  /diary ...  |
+-----------------------------------------------------------------------+
                                   |
+-----------------------------------------------------------------------+
|                     LangGraph Multi-Agent System                      |
| (Planner, Nav, Budget, Hotel, Restaurant, Safety, Weather, Vision...) |
+-----------------------------------------------------------------------+
                                   |
+-----------------------------------------------------------------------+
|                    SCIF 8-Engine Cognitive Layer                      |
| UserProfile | Memory | Context | Planning | Rec | Explain | Adapt | Risk|
+-----------------------------------------------------------------------+
           |                                             |
+----------------------+                       +-----------------------+
|  FAISS Vector Store  |                       | External APIs & Data  |
|  & Firestore Database|                       | Gemini, Weather, ORS, |
|                      |                       | OpenTripMap, Wiki     |
+----------------------+                       +-----------------------+
```

---

## ⚙️ SCIF 8-Engine Cognitive Layer

1. **UserProfileEngine**: Stores declared user preferences (budget, dietary, travel style) with in-memory caching.
2. **MemoryEngine**: Computes similarity over long-term preference vectors using FAISS, updates behavioral feature weights, and executes inference promotion.
3. **ContextEngine**: Evaluates live climate data (Open-Meteo), transport delays, crowd density, opening hours, festival bonuses, and emergency advisories to compute `Context Score` and `Context Confidence`.
4. **PlanningEngine**: Drives the 12-agent graph execution and post-processes candidate activities through the recommendation matrix.
5. **RecommendationEngine**: Runs the 12-stage scoring algorithm: User Profile → Memory → Budget → Distance → Interest → Weather → Crowd → Safety → Opening Hours → Context Score → Gemini Reasoning → Explainability → Final Recommendation.
6. **ExplainabilityEngine**: Assembles transparent, traceable score rationales and supporting evidence.
7. **AdaptiveLearningEngine**: Evaluates dynamic re-planning triggers (weather change, traffic delays, place closed) and handles online feedback loops.
8. **RiskAssessmentEngine**: Audits travel safety, weather advisories, and emergency alerts to produce a composite risk score between 0.0 and 1.0.

---

## 🤖 LangGraph 12-Agent Architecture

The 12 specialized autonomous agents share a unified state graph (`SmartTripState`):
- `PlannerAgent`: Generates initial itinerary skeleton.
- `NavigationAgent`: Computes MapLibre turn-by-turn routes and ETAs.
- `BudgetAgent`: Optimizes category allocation.
- `HotelAgent`: Matches accommodation options.
- `RestaurantAgent`: Selects culinary dining options.
- `SafetyAgent`: Audits safety and emergency alerts.
- `WeatherAgent`: Evaluates outdoor climate suitability.
- `VisionAgent`: Analyzes landmark photo inputs via Gemini Vision.
- `TourGuideAgent`: Synthesizes audio story scripts.
- `ExpenseAgent`: Tracks live trip expenditures.
- `DiaryAgent`: Creates AI daily journals.
- `AnalyticsAgent`: Computes recommendation metrics.
