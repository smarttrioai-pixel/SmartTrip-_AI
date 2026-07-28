# SmartTrip AI

> **Subtitle**: A Cognitive Memory-Augmented Multimodal Travel Assistant for Personalized Intelligent Tourism
> **Target Standards**: IEEE Conference Publication, Scopus Journal Extension, Startup MVP, Production Deployment, Final Year Major Project

SmartTrip AI is a production-grade, memory-augmented multimodal travel platform powered by an 8-Engine SCIF Cognitive Framework and a 12-Agent Autonomous LangGraph System.

---

## 🌟 Key Features

- **8-Engine SCIF Cognitive Framework**:
  - `UserProfileEngine`: Manages declared user preferences with low-latency caching.
  - `MemoryEngine`: FAISS vector similarity search, long-term preference embeddings, short-term history, and behavioral weight promotion.
  - `ContextEngine`: Evaluates real-time weather, traffic/transport, crowd density, opening hours, festival detection, and emergency alerts.
  - `PlanningEngine`: Orchestrates multi-agent execution with SCIF post-processing.
  - `RecommendationEngine`: Complete 12-Stage Recommendation Pipeline (User Profile → Memory → Budget → Distance → Interest → Weather → Crowd → Safety → Opening Hours → Context Score → Gemini Reasoning → Explainability → Final Recommendation).
  - `ExplainabilityEngine`: Multi-score explainability breakdown with supporting evidence.
  - `AdaptiveLearningEngine`: Continuous memory feedback loop and dynamic re-planning trigger evaluation.
  - `RiskAssessmentEngine`: Multi-factor safety, weather advisory, and emergency risk scoring.

- **12 Autonomous LangGraph Agents**:
  - `PlannerAgent`, `NavigationAgent`, `BudgetAgent`, `HotelAgent`, `RestaurantAgent`, `SafetyAgent`, `WeatherAgent`, `VisionAgent`, `TourGuideAgent`, `ExpenseAgent`, `DiaryAgent`, `AnalyticsAgent`.

- **Multimodal WebXR & Gemini Vision AR Explore**:
  - Camera landmark recognition, WebXR AR overlay cards, audio story narration, and interactive landmark Q&A.

- **MapLibre Interactive Navigation**:
  - Turn-by-turn directions, walking/driving/cycling modes, ETA calculations, "Take Me There" routing, and voice guidance.

- **Travel Diary & Analytics Dashboard**:
  - AI daily journal, photo timeline, expense audit, downloadable **Shareable PDF**, and **CSV Analytics Export**.

---

## 🚀 Quick Start

### 1. Backend Setup (FastAPI)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Swagger UI Documentation available at: `http://localhost:8000/docs`

### 2. Frontend Setup (Next.js 14)

```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000` in your browser.

---

## 🐳 Docker Deployment

To launch the full production stack using Docker Compose:

```bash
docker-compose up --build -d
```

---

## 📖 Documentation Directory

- [`ARCHITECTURE.md`](./ARCHITECTURE.md) - System architecture and SCIF engine design.
- [`API_DOCUMENTATION.md`](./API_DOCUMENTATION.md) - API endpoints & Pydantic schemas.
- [`DEPLOYMENT_GUIDE.md`](./DEPLOYMENT_GUIDE.md) - Docker, Render, Vercel & CI/CD deployment guide.
- [`IEEE_RESEARCH_NOTES.md`](./IEEE_RESEARCH_NOTES.md) - IEEE paper contribution & novel methodology.
- [`PROJECT_STATUS_REPORT.md`](./PROJECT_STATUS_REPORT.md) - System audit and completed features.