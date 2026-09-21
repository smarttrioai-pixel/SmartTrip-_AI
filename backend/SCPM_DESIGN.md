# SCPM Design Document
## SmartTrip Cognitive Personalization Model

**Version:** SCPM-v1  
**Date:** 2026-09-20  
**Status:** Implemented

---

## 1. Motivation

SmartTrip's existing `RecommendationEngine` uses a **heuristic** `_score_personalization()` that maps behavioral `feature_weights` (updated by rule-based SGD) to a 0.0–1.0 score. This produces reasonable rankings but is not a learned model — it cannot capture complex, nonlinear interactions between user preferences and activity features.

SCPM introduces a **trainable supervised ML model** (Logistic Regression) that:
- Learns P(user accepts activity) from real feedback events
- Captures interactions between activity attributes and user behavioral profile
- Provides auditable, explainable coefficients
- Replaces the heuristic score only when trained (cold-start safety)
- Is completely separate from and complementary to the LLM reasoning

---

## 2. Architecture

```
User submits feedback (accept/reject)
        ↓
POST /memory/feedback
        ↓
MemoryEngine.record_activity_event()
  ├─ Updates behavioral feature_weights in Firestore (existing)
  ├─ Writes FeedbackMemory doc to memory_feedback/ (existing)
  └─ Writes SCPMTrainingRecord to
     scpm_training_records/{uid}/records/{id}     ← NEW
        ↓
When records_since_last_train >= SCPM_RETRAIN_THRESHOLD (10):
  SCPMTrainer.train(user_id, records)
        ↓
  LogisticRegression(class_weight='balanced')
        ↓
  ModelMetadata (coefficients) saved to
  users/{uid}/personalization_model/current       ← NEW
        ↓
At next trip generation (PlanningEngine Stage 9):
  SCPMRepository.get_model_metadata(user_id)
        ↓
  SCPMPredictor.predict() → P(accept)
        ↓
  personalization_score = P(accept)
  [replaces heuristic _score_personalization()]
```

---

## 3. Feature Vector Design

**Total features:** 16 (no label leakage)

| Dim | Feature | Source | Range |
|-----|---------|--------|-------|
| 0–6 | Category OHE | Activity schema (from LLM) | {0,1} |
| 7 | cost_ratio | estimated_cost / daily_budget | [0, 3] |
| 8 | weather_score | ContextEngine (Open-Meteo) | [0, 1] |
| 9 | opening_hrs_score | ContextEngine (time-based) | [0, 1] |
| 10 | context_composite | ContextEngine composite | [0, 1] |
| 11 | budget_sensitivity | memory_behavioral/{uid} | [−1, 1] |
| 12 | crowd_aversion | memory_behavioral/{uid} | [−1, 1] |
| 13 | novelty_seeking | memory_behavioral/{uid} | [−1, 1] |
| 14 | distance_tolerance | memory_behavioral/{uid} | [−1, 1] |
| 15 | pace_preference | memory_behavioral/{uid} | [−1, 1] |

**Label:**  
`y = 1` (accept/like), `y = 0` (reject/dislike)  
Edit events are excluded (ambiguous label).

**No leakage guarantee:** All features are observed BEFORE the user gives feedback. The label is computed from the feedback event itself and never included in the feature vector.

---

## 4. Model

**Algorithm:** `sklearn.linear_model.LogisticRegression`

```python
LogisticRegression(
    max_iter=1000,
    class_weight="balanced",   # handles imbalanced positive/negative ratio
    solver="lbfgs",
    C=1.0,
    random_state=42,
)
```

**Preprocessing:** `StandardScaler` fitted on training data. Parameters stored alongside coefficients for inference reconstruction.

**Why LR?**
- Interpretable (coefficients = log-odds contribution per feature)
- Efficient (< 50ms on 10–1000 samples)
- Calibrated probabilities suitable for direct use as scores
- No hyperparameter tuning required for initial deployment

---

## 5. Storage Schema

### Training Records
```
Firestore: scpm_training_records/{user_id}/records/{record_id}

Fields: id, user_id, trip_id, activity_title, category,
        estimated_cost, daily_budget_hint,
        weather_score, opening_hrs_score, context_composite,
        budget_sensitivity, crowd_aversion, novelty_seeking,
        distance_tolerance, pace_preference,
        label (1|0), event_type, rejection_reason, created_at
```

### Model Metadata
```
Firestore: users/{user_id}/personalization_model/current

Fields: status, model_version, sample_count, positive_count,
        negative_count, accuracy, baseline_accuracy, precision,
        recall, f1, roc_auc,
        coefficients (list[float], N=16),
        intercept (float),
        feature_names (list[str]),
        scaler_mean (list[float]),
        scaler_scale (list[float]),
        trained_at, last_updated, records_since_last_train
```

**Why not pickle?** Plain float lists are safe, auditable, and Firestore-compatible. The sklearn model is reconstructed at inference time (< 1ms overhead).

---

## 6. Cold-Start Policy

| Condition | Action |
|-----------|--------|
| `total < 10` | Model inactive, heuristic used |
| `positive < 3` | Model inactive, heuristic used |
| `negative < 3` | Model inactive, heuristic used |
| All thresholds met | Training proceeds |

Status returned honestly via `GET /personalization/model-status`. No fake "model active" messages.

---

## 7. Integration Points

| Component | Change | Purpose |
|-----------|--------|---------|
| `MemoryEngine.record_activity_event()` | Writes SCPMTrainingRecord | Data collection |
| `PlanningEngine` Stage 9 | Loads SCPM metadata | Pre-scoring |
| `RecommendationEngine.score_and_rank()` | Calls SCPMPredictor | Scoring |
| `POST /personalization/train` | Manual training trigger | Research/ops |
| `GET /personalization/model-status` | Observability | Monitoring |
| `GET /personalization/explanation` | Coefficient export | Explainability |
| `GET /analytics/dashboard` | SCPM status included | User-facing |

---

## 8. Explainability

Feature coefficients are positive (increase P(accept)) or negative (decrease P(accept)). They can be directly reported to the user via `GET /personalization/explanation` as "what factors most influence your recommendations."

Example output:
```json
{
  "top_positive_factors": [
    {"feature": "cat_attraction", "coefficient": 1.23, "interpretation": "Tourist attractions / landmarks"},
    {"feature": "weather_score", "coefficient": 0.87, "interpretation": "Weather suitability"}
  ],
  "top_negative_factors": [
    {"feature": "cost_ratio", "coefficient": -0.94, "interpretation": "Activity cost relative to daily budget"}
  ]
}
```

---

## 9. Auto-Retraining

When `records_since_last_train >= SCPM_RETRAIN_THRESHOLD` (default 10), `MemoryEngine._auto_retrain()` triggers in-process retraining. This is acceptable because:
- LR on 10–1000 samples takes < 50ms
- The feedback endpoint is already an async Firestore write
- Retraining failure silently falls back to existing model (non-critical)

The threshold is configurable via `SCPM_RETRAIN_THRESHOLD` constant in `memory_engine.py`.

---

## 10. Limitations (Honest Assessment)

| Limitation | Status |
|------------|--------|
| Small dataset per user | Inherent to cold-start; addressed by balanced LR and cold-start threshold |
| Traffic/crowd context features are unavailable | ContextEngine returns 0.5; acknowledged in feature design |
| No real-time feature drift detection | Future work |
| Single model per user (no global model) | Intentional: privacy-preserving, research-motivated |
| Evaluation requires n ≥ 20 for meaningful split | Reported honestly; smaller datasets use full-fit metrics only |
