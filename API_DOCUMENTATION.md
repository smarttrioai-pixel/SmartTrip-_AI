# SmartTrip AI: API Documentation

> **FastAPI Base Path**: `/api/v1`

---

## 📌 Endpoints Summary

### 1. Navigation Router (`/api/v1/navigation`)
- `GET /geocode`: Geocode place names to coordinates using OpenStreetMap Nominatim.
  - Query params: `q` (string)
- `GET /route`: Calculate turn-by-turn route, distance, duration, and steps.
  - Query params: `origin_lat`, `origin_lon`, `dest_lat`, `dest_lon`, `mode` (`walking|driving|cycling`)
- `GET /nearby`: Fetch nearby POIs using OpenTripMap.
  - Query params: `lat`, `lon`, `radius_m`

### 2. Explore & AR Router (`/api/v1/explore`)
- `POST /analyze-landmark`: Perform multimodal landmark recognition via Gemini Vision.
  - Request body: `{ "prompt_hint": "string", "image_b64": "string" }`
- `GET /landmark-info`: Fetch Wikipedia summary and historical background.
  - Query params: `name` (string)
- `POST /qa`: Interactive landmark Q&A.
  - Request body: `{ "landmark_name": "string", "question": "string" }`

### 3. Travel Diary Router (`/api/v1/diary`)
- `POST /generate`: Generate AI daily journal, story summary, and expense audit.
  - Request body: `{ "trip_id": "string", "destination": "string", "highlights": ["string"] }`
- `GET /export-pdf/{trip_id}`: Export shareable PDF summary report for download.

### 4. Analytics Router (`/api/v1/analytics`)
- `GET /dashboard`: Fetch travel statistics, budget analysis, category split, and recommendation accuracy.
  - Query params: `user_id` (string)
- `GET /export-csv`: Export travel metrics and recommendation data as CSV.

### 5. Trips Router (`/api/v1/trips`)
- `POST /plan`: Generate AI trip itinerary using LangGraph 12-agent system.
- `GET /`: List saved trips.
- `POST /{trip_id}/save`: Save trip to profile.

### 6. Profile & Memory Routers (`/api/v1/profile`, `/api/v1/memory`)
- `GET /profile/me`: Fetch declared user preferences and profile.
- `PUT /profile/preferences`: Update preferences.
- `GET /memory/insights`: Retrieve long-term preference embeddings and learned tendencies.
