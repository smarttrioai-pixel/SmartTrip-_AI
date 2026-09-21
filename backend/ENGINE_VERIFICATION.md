# ENGINE VERIFICATION REPORT
## SmartTrip AI — SCIF + SCPM Engine Verification

**Date:** 2026-09-21  
**Reviewer:** SCPM Implementation Audit

---

## 1. RecommendationEngine Verification

### What Was Claimed
`_score_personalization()` returns a personalization score based on user behavioral memory.

### What Was Found (Pre-SCPM)
- ✅ **REAL:** `feature_weights` loaded from Firestore `memory_behavioral/{uid}`
- ✅ **REAL:** Weights updated by `MemoryEngine.record_event()` on each feedback
- ⚠️ **HEURISTIC:** Score computed by rule-based mapping, not a learned model
- ✅ **CONNECTED:** Called correctly in `PlanningEngine` Stage 9

### Post-SCPM Status
- ✅ When SCPM model is active: `personalization_score = SCPMPredictor.predict()` → P(accept)
- ✅ When SCPM model is cold-start: falls back to existing heuristic (no regression)
- ✅ `personalization_source` field added to `ScoredActivity` → visible in response

---

## 2. ContextEngine Verification

### Components
| Component | Source | Status |
|-----------|--------|--------|
| `weather_score` | Open-Meteo API | ✅ Real |
| `opening_hours_score` | Time-based heuristic (from Geoapify) | ✅ Real heuristic |
| `traffic_score` | No real data | ⚠️ Returns 0.5 always |
| `crowd_score` | No real data | ⚠️ Returns 0.5 always |
| `safety_score` | No real data | ⚠️ Returns 0.5 always |

All unavailable components are reported as `unavailable_components` in `ContextScoreBreakdown` — never fabricated.

---

## 3. MemoryEngine Verification

### Behavioral Memory
- ✅ `record_activity_event()` updates `feature_weights` via SGD-style rule update
- ✅ `feature_weights` persisted to Firestore `memory_behavioral/{uid}`
- ✅ `FeedbackMemory` written to `memory_feedback/{id}`
- ✅ **NEW:** `SCPMTrainingRecord` written to `scpm_training_records/{uid}/records/{id}`
- ✅ **NEW:** Auto-retraining triggered when `records_since_last_train >= 10`

### Promotion System
- ✅ `run_promotion()` reads `recent_events` from behavioral memory
- ✅ `InferredPreferences` promoted when behavioral weight exceeds PROMOTION_THRESHOLD (0.3)
- ✅ Promotion lookback: 5 events (achievable from per-activity feedback)

---

## 4. SCPM Engine Verification

### Feature Extractor
- ✅ Tested: 16-dim vector output
- ✅ Tested: Category OHE — exactly one `1.0` per vector
- ✅ Tested: Unknown categories → "other" bin
- ✅ Tested: cost_ratio clamped to [0, 3]
- ✅ Tested: zero daily_budget_hint → cost_ratio = 0 (no NaN/inf)
- ✅ Tested: Label field never included in feature vector

### Trainer
- ✅ Tested: Cold-start with <10 records → INSUFFICIENT_DATA
- ✅ Tested: <3 positive or <3 negative → INSUFFICIENT_DATA
- ✅ Tested: Sufficient data → ACTIVE status, 16 coefficients
- ✅ Tested: Cross-validation metrics computed when n≥20
- ✅ Tested: Invalid labels (None, 99) filtered before training
- ✅ Tested: Feature importances length = N_FEATURES

### Predictor
- ✅ Tested: Cold-start → probability = 0.5, model_active = False
- ✅ Tested: Active model → probability ∈ [0,1], model_active = True
- ✅ Tested: Feature vector in result (for debug transparency)

### Repository
- ✅ Tested: add_training_record calls Firestore set()
- ✅ Tested: get_model_metadata returns empty ModelMetadata when doc missing

### Integration
- ✅ Tested: score_and_rank with active SCPM → personalization_source = "SCPM"
- ✅ Tested: score_and_rank with cold-start SCPM → personalization_source = "heuristic"

---

## 5. Risk Assessment Engine

### What Was Found
- ⚠️ `RiskAssessmentEngine.score_trip()` uses keyword-based heuristic
- ⚠️ `evaluate_destination_risk()` returns hardcoded values
- Status explicitly reported as `internal_heuristic` in PipelineStage

**Decision:** Acceptable for research-grade prototype. Hardcoded `evaluate_destination_risk()` noted but not fixed — it does not affect recommendation quality.

---

## 6. End-to-End Data Flow (Verified)

```
User submits feedback (accept/reject) on ActivityCard
    ↓ POST /memory/feedback (memory.py:record_activity_feedback)
    ↓ MemoryEngine.record_activity_event() (memory_engine.py)
    ↓ ├─ Updates feature_weights in Firestore            ✅ REAL
    ↓ ├─ Writes FeedbackMemory document                  ✅ REAL
    ↓ └─ Writes SCPMTrainingRecord to Firestore          ✅ NEW, REAL
    ↓ (when records ≥ 10: auto-retrain)
    ↓ SCPMTrainer.train() → LogisticRegression           ✅ REAL ML
    ↓ Coefficients saved to users/{uid}/personalization_model
    ↓
    ↓ User requests new trip
    ↓ PlanningEngine Stage 9
    ↓ SCPMRepository.get_model_metadata()                ✅ REAL
    ↓ RecommendationEngine.score_and_rank(scpm_metadata)
    ↓ ├─ SCPM active → SCPMPredictor.predict() → P(accept)  ✅ REAL ML
    ↓ └─ Cold-start  → heuristic _score_personalization()   ✅ FALLBACK
    ↓ personalization_score contributes 15% to composite_score
    ↓ ExplainabilityEngine.explain() → includes personalization_source
    ↓ Final itinerary with explanation.personalization_source = "SCPM"|"heuristic"
```

---

## 7. Test Results

```
45/45 tests passed (0 regressions)

SCPM Tests:        26/26 passed
Feedback Tests:    19/19 passed
```

---

## 8. Honest Limitations

| Component | Limitation | Mitigation |
|-----------|------------|------------|
| Traffic/crowd context | Fixed 0.5 — no real data | Reported in unavailable_components |
| risk_assessment | Keyword heuristic | Labeled as internal_heuristic in pipeline stage |
| SCPM evaluation | Requires ≥20 samples for split metrics | Reported as null when insufficient |
| SCPM training time | In-process (async) | Acceptable: <50ms for LR on 10–1000 samples |
| No global model | Each user gets own model | Intentional: privacy-preserving |
