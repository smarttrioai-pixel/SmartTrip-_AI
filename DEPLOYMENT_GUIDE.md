# SmartTrip AI: Deployment & Production Guide

This guide details how to deploy SmartTrip AI to local Docker, Render (Backend), Vercel (Frontend), and setting up CI/CD via GitHub Actions.

---

## 1. Environment Variables

Create `.env` files in `backend/` and `frontend/`:

### Backend `.env`
```env
APP_NAME=SmartTrip AI
ENVIRONMENT=production
DEBUG=False
GEMINI_API_KEY=your_gemini_api_key
OPENWEATHER_API_KEY=your_weather_api_key
OPENROUTESERVICE_API_KEY=your_ors_api_key
OPENTRIPMAP_API_KEY=your_opentripmap_api_key
FIREBASE_CREDENTIALS_PATH=app/core/firebase_creds.json
```

---

## 2. Docker & Docker Compose

To build and launch the production container stack:

```bash
docker-compose up --build -d
```
Backend will run at `http://localhost:8000`, Frontend at `http://localhost:3000`.

---

## 3. Cloud Deployment

### Backend on Render
- Deployment file: `render.yaml`
- Root directory: `backend`
- Environment: Python 3.11
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### Frontend on Vercel
- Deployment file: `frontend/vercel.json`
- Framework Preset: Next.js
- Build Command: `npm run build`

---

## 4. CI/CD GitHub Actions Workflow

Workflow file located at `.github/workflows/ci-cd.yml`:
- Runs automated pytest test suite on Python 3.11.
- Runs Next.js strict build check on Node.js 18.
