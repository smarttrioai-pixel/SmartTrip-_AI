"""
SCPM Trainer — trains a Logistic Regression model on user feedback records.

Design decisions:
  - Model: LogisticRegression(class_weight='balanced') — handles class imbalance
    without requiring equal positive/negative counts.
  - Scaler: StandardScaler applied before LR — important for coefficient
    interpretability and convergence speed.
  - Evaluation: uses stratified split when n >= 20, otherwise leave-one-out
    cross-validation. Reports "insufficient_data" honestly when n < threshold.
  - Coefficients stored as plain lists (not pickle) for Firestore compatibility.
  - Model is only marked ACTIVE if training is valid (metrics computed).

Cold-start policy (from config, defaults):
  SCPM_MIN_TOTAL_SAMPLES = 10
  SCPM_MIN_POSITIVE_SAMPLES = 3
  SCPM_MIN_NEGATIVE_SAMPLES = 3
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler

from app.cognitive.scpm.feature_extractor import FEATURE_NAMES, FeatureExtractor
from app.cognitive.scpm.model_metadata import ModelMetadata, ModelStatus

logger = logging.getLogger(__name__)

# Cold-start thresholds (override via env: SCPM_MIN_TOTAL_SAMPLES etc.)
MIN_TOTAL_SAMPLES = 10
MIN_POSITIVE_SAMPLES = 3
MIN_NEGATIVE_SAMPLES = 3

# Minimum samples needed for a train/validation split
MIN_FOR_SPLIT = 20


class SCPMTrainer:
    """
    Trains a Logistic Regression model from SCPMTrainingRecord dicts.

    Usage:
        trainer = SCPMTrainer()
        metadata = trainer.train(user_id="uid", records=[...])
    """

    def __init__(
        self,
        min_total: int = MIN_TOTAL_SAMPLES,
        min_positive: int = MIN_POSITIVE_SAMPLES,
        min_negative: int = MIN_NEGATIVE_SAMPLES,
    ) -> None:
        self._min_total = min_total
        self._min_positive = min_positive
        self._min_negative = min_negative
        self._extractor = FeatureExtractor()

    def train(self, user_id: str, records: list[dict]) -> ModelMetadata:
        """
        Train SCPM on labelled records. Returns updated ModelMetadata.

        records: list of SCPMTrainingRecord.to_dict() outputs.
        Each record must have a 'label' key: 1 (accept) or 0 (reject).

        The caller (SCPMRepository) is responsible for retrieving records.
        """
        meta = ModelMetadata(user_id=user_id)
        meta.sample_count = len(records)

        # ---- 1. Validate labels ----
        valid = [r for r in records if r.get("label") in (0, 1)]
        if len(valid) < len(records):
            logger.warning(
                "SCPM_TRAIN_WARN user=%s dropped %d records with invalid labels",
                user_id, len(records) - len(valid),
            )
        records = valid
        n = len(records)

        labels = [r["label"] for r in records]
        n_pos = sum(labels)
        n_neg = n - n_pos
        meta.sample_count = n
        meta.positive_count = n_pos
        meta.negative_count = n_neg

        # ---- 2. Cold-start check ----
        if n < self._min_total or n_pos < self._min_positive or n_neg < self._min_negative:
            logger.info(
                "SCPM_COLD_START user=%s total=%d pos=%d neg=%d — model inactive",
                user_id, n, n_pos, n_neg,
            )
            meta.status = ModelStatus.INSUFFICIENT_DATA
            return meta

        # ---- 3. Build feature matrix ----
        X = np.array([self._extractor.extract_from_record(r) for r in records], dtype=np.float64)
        y = np.array(labels, dtype=np.int32)

        # ---- 4. Scale features ----
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # ---- 5. Train model ----
        lr = LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
            solver="lbfgs",
            C=1.0,
            random_state=42,
        )

        # ---- 6. Evaluate ----
        if n >= MIN_FOR_SPLIT:
            # Stratified K-Fold cross-validation (k=3 for small datasets)
            k = min(5, max(3, n // 10))
            cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=42)
            y_pred = cross_val_predict(lr, X_scaled, y, cv=cv)
            y_prob = cross_val_predict(lr, X_scaled, y, cv=cv, method="predict_proba")[:, 1]

            meta.accuracy = float(accuracy_score(y, y_pred))
            meta.baseline_accuracy = float(max(n_pos, n_neg) / n)
            meta.precision = float(precision_score(y, y_pred, zero_division=0))
            meta.recall = float(recall_score(y, y_pred, zero_division=0))
            meta.f1 = float(f1_score(y, y_pred, zero_division=0))
            try:
                meta.roc_auc = float(roc_auc_score(y, y_prob))
            except ValueError:
                meta.roc_auc = None

            logger.info(
                "SCPM_EVAL user=%s n=%d acc=%.3f baseline=%.3f f1=%.3f",
                user_id, n, meta.accuracy, meta.baseline_accuracy, meta.f1,
            )
        else:
            # Dataset too small for meaningful split — report honestly
            meta.accuracy = None
            meta.baseline_accuracy = float(max(n_pos, n_neg) / n)
            meta.precision = None
            meta.recall = None
            meta.f1 = None
            meta.roc_auc = None
            logger.info(
                "SCPM_EVAL_SKIP user=%s n=%d — too small for meaningful evaluation",
                user_id, n,
            )

        # ---- 7. Final fit on all data ----
        lr.fit(X_scaled, y)

        # ---- 8. Store coefficients ----
        meta.coefficients = lr.coef_[0].tolist()
        meta.intercept = float(lr.intercept_[0])
        meta.feature_names = list(FEATURE_NAMES)
        meta.scaler_mean = scaler.mean_.tolist()
        meta.scaler_scale = scaler.scale_.tolist()

        meta.status = ModelStatus.ACTIVE
        meta.trained_at = datetime.now(timezone.utc)
        meta.last_updated = datetime.now(timezone.utc)
        meta.records_since_last_train = 0

        logger.info(
            "SCPM_TRAINED user=%s status=active coefficients=%d",
            user_id, len(meta.coefficients),
        )
        return meta

    def get_feature_importances(self, meta: ModelMetadata) -> list[dict]:
        """
        Return sorted list of (feature_name, coefficient) pairs.
        Coefficients represent log-odds — positive means more likely to accept.
        """
        if not meta.coefficients or not meta.feature_names:
            return []
        pairs = sorted(
            zip(meta.feature_names, meta.coefficients),
            key=lambda x: abs(x[1]),
            reverse=True,
        )
        return [{"feature": name, "coefficient": round(coef, 4)} for name, coef in pairs]
