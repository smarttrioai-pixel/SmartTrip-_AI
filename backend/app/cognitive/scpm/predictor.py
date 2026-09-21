"""
SCPM Predictor — reconstructs a trained Logistic Regression from stored
coefficients and returns a preference probability.

Design: we reconstruct the sklearn model from the serialised coefficients
and scaler parameters stored in Firestore (no pickle, no binary files).

When the model is inactive (cold-start), returns a neutral score of 0.5
so the caller can fall back to the existing heuristic.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from app.cognitive.scpm.feature_extractor import FeatureExtractor, N_FEATURES
from app.cognitive.scpm.model_metadata import ModelMetadata

logger = logging.getLogger(__name__)


@dataclass
class PredictionResult:
    probability: float          # P(user accepts this activity), 0.0–1.0
    model_active: bool          # False when cold-start or no model
    model_version: str
    personalization_source: str  # "SCPM" or "heuristic"
    feature_vector: list[float]  # for debugging/transparency
    feature_names: list[str]


class SCPMPredictor:
    """
    Reconstructs a LogisticRegression from stored ModelMetadata coefficients
    and returns a preference probability for a given feature vector.

    Thread-safe: stateless, no shared mutable state.
    """

    def __init__(self) -> None:
        self._extractor = FeatureExtractor()

    def predict(
        self,
        meta: ModelMetadata,
        *,
        category: str,
        estimated_cost: float,
        daily_budget_hint: float,
        weather_score: float,
        opening_hrs_score: float,
        context_composite: float,
        budget_sensitivity: float,
        crowd_aversion: float,
        novelty_seeking: float,
        distance_tolerance: float,
        pace_preference: float,
    ) -> PredictionResult:
        """
        Predict P(accept) for a single activity.

        Returns PredictionResult with model_active=False and probability=0.5
        when the model has not been trained yet (cold-start).
        """
        features = self._extractor.extract(
            category=category,
            estimated_cost=estimated_cost,
            daily_budget_hint=daily_budget_hint,
            weather_score=weather_score,
            opening_hrs_score=opening_hrs_score,
            context_composite=context_composite,
            budget_sensitivity=budget_sensitivity,
            crowd_aversion=crowd_aversion,
            novelty_seeking=novelty_seeking,
            distance_tolerance=distance_tolerance,
            pace_preference=pace_preference,
        )

        if not meta.is_active:
            return PredictionResult(
                probability=0.5,
                model_active=False,
                model_version=meta.model_version,
                personalization_source="heuristic",
                feature_vector=features,
                feature_names=meta.feature_names or [],
            )

        try:
            prob = self._reconstruct_and_predict(meta, features)
        except Exception as exc:
            logger.warning("SCPM_PREDICT_ERROR user=%s error=%s", meta.user_id, exc)
            prob = 0.5
            return PredictionResult(
                probability=prob,
                model_active=False,
                model_version=meta.model_version,
                personalization_source="heuristic",
                feature_vector=features,
                feature_names=meta.feature_names,
            )

        return PredictionResult(
            probability=round(prob, 4),
            model_active=True,
            model_version=meta.model_version,
            personalization_source="SCPM",
            feature_vector=features,
            feature_names=meta.feature_names,
        )

    @staticmethod
    def _reconstruct_and_predict(meta: ModelMetadata, features: list[float]) -> float:
        """
        Reconstruct sklearn objects from stored parameters and predict.
        """
        n = N_FEATURES

        # Validate stored parameters match current feature set
        if len(meta.coefficients) != n:
            raise ValueError(
                f"Coefficient dimension mismatch: stored={len(meta.coefficients)} expected={n}"
            )
        if len(meta.scaler_mean) != n or len(meta.scaler_scale) != n:
            raise ValueError("Scaler parameters dimension mismatch")

        # Reconstruct StandardScaler
        scaler = StandardScaler()
        scaler.mean_ = np.array(meta.scaler_mean, dtype=np.float64)
        scaler.scale_ = np.array(meta.scaler_scale, dtype=np.float64)
        scaler.n_features_in_ = n

        # Reconstruct LogisticRegression
        lr = LogisticRegression()
        lr.coef_ = np.array([meta.coefficients], dtype=np.float64)
        lr.intercept_ = np.array([meta.intercept], dtype=np.float64)
        lr.classes_ = np.array([0, 1])

        # Scale + predict
        x = np.array([features], dtype=np.float64)
        x_scaled = scaler.transform(x)
        prob = lr.predict_proba(x_scaled)[0, 1]
        return float(prob)

    def predict_from_record(self, meta: ModelMetadata, record: dict) -> PredictionResult:
        """Convenience: predict from a SCPMTrainingRecord dict."""
        return self.predict(
            meta,
            category=record.get("category", "other"),
            estimated_cost=record.get("estimated_cost", 0.0),
            daily_budget_hint=record.get("daily_budget_hint", 0.0),
            weather_score=record.get("weather_score", 0.5),
            opening_hrs_score=record.get("opening_hrs_score", 0.75),
            context_composite=record.get("context_composite", 0.5),
            budget_sensitivity=record.get("budget_sensitivity", 0.0),
            crowd_aversion=record.get("crowd_aversion", 0.0),
            novelty_seeking=record.get("novelty_seeking", 0.0),
            distance_tolerance=record.get("distance_tolerance", 0.0),
            pace_preference=record.get("pace_preference", 0.0),
        )
