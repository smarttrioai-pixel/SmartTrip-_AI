# SmartTrip AI 2.0 — Phase 0 + Phase 1 (Auth & Profile, Firebase stack)

Reflects the v3 master prompt: Firebase Authentication as the sole auth
system, Cloud Firestore as the only database, Gemini for AI. Google
Maps/MapLibre/OpenRouteService/OpenTripMap and the LangGraph multi-agent
pipeline are later phases — see the roadmap doc for the full plan.

## 1. What changed in this pass (Phase 0)

The previous session's custom email/password JWT backend has been **removed
entirely** and replaced with Firebase Authentication:

- **Removed:** `app/core/security.py` (bcrypt/JWT), `app/services/auth_service.py`,
  `app/schemas/auth.py`, `app/api/routes/auth.py`, and the frontend's manual
  token-refresh interceptor logic.
- **Added:** `app/core/firebase.py::verify_firebase_token` — verifies a
  Firebase ID token and returns its claims. `get_current_user` in
  `app/api/deps.py` now verifies the token and lazily creates the Firestore
  profile doc on first sight of a uid (covers Google sign-in and any client
  that skips the explicit sync call).
- **Frontend:** `useSignup`/`useLogin`/`useGoogleLogin`/`useForgotPassword`
  now call the Firebase client SDK directly (`createUserWithEmailAndPassword`,
  `signInWithEmailAndPassword`, `signInWithPopup`, `sendPasswordResetEmail`).
  `apiClient`'s request interceptor calls `currentUser.getIdToken()` fresh on
  every request — Firebase handles token refresh internally, so the
  hand-rolled 401-refresh-retry dance from the old JWT setup is gone.
  `AuthStateListener` (mounted in `Providers`) subscribes to
  `onIdTokenChanged` and is the actual source of truth for "is logged in";
  the Zustand store just mirrors it for convenient reads (sidebar, middleware
  cookie).

## 2. What's new in this pass (Phase 1: Profile module)

Full profile feature, frontend + backend:
- `GET/PUT /profile`, `PUT /profile/preferences`, `POST /profile/sync`
- Frontend `features/profile/`: forms for full name and travel preferences
  (budget, currency, language, travel style, food preference, accommodation,
  transport, interests) with loading/error/empty states and optimistic-feeling
  save confirmations.
- Two new shared UI primitives: `Select` and `ChipGroup` (multi-select tags,
  used for interests).

## 3. Also new: splash screen + forgot password

- `/` is now an animated splash screen (Framer Motion, SVG route-line motif
  matching the `(auth)` layout's branding) that waits for Firebase to restore
  the session, then routes to `/home` or `/login`.
- `/forgot-password` — Firebase's `sendPasswordResetEmail`, no backend
  endpoint needed for this one; success state shown inline.

## 4. Dashboard shell

`(dashboard)` route group with a sidebar (desktop) / bottom tab bar (mobile):
Dashboard, AI Trip Planner, AI Chat, Saved Trips, Profile. Trip Planner, Chat,
and Saved Trips are placeholder pages right now — their real implementation
is scoped to later roadmap phases (see below) since each is a substantial
module in its own right (LangGraph agent pipeline, MapLibre, etc.) and the
master prompt calls for approving each phase before building it.

## 5. Setup

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set FIREBASE_PROJECT_ID, GEMINI_API_KEY
# Auth: either set FIREBASE_SERVICE_ACCOUNT_JSON to a service account file path,
# or run `gcloud auth application-default login` for local dev.
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_FIREBASE_* and NEXT_PUBLIC_API_BASE_URL
npm run dev
```

**Firebase Console setup required:** enable Email/Password and Google sign-in
providers under Authentication → Sign-in method. No API-key-based Google Maps
setup is needed anymore.

## 6. Testing

```bash
cd backend
pytest -v
```
`tests/test_deps.py` covers: missing credentials → 401, invalid token → 401,
first-login lazy profile creation, and reuse of an existing profile — all
against a fake in-memory repository with `verify_firebase_token` monkeypatched,
so no real Firebase project or database is needed to run these.

Frontend component/interceptor tests are still a to-do, same as noted in the
previous pass.

## 7. Next phases (per the roadmap — pick one)

- **Phase 2:** Chat Assistant UI (backend already works) + basic AI Trip
  Planner UI (single-shot Gemini call, not yet the agent pipeline)
- **Phase 3:** Rebuild itinerary generation as a LangGraph multi-agent
  pipeline with explainability/confidence scoring
- **Phase 4:** MapLibre + OpenRouteService navigation ("Take Me There")

See `SmartTrip_AI_Architecture_Roadmap.md` for the full phase list.
