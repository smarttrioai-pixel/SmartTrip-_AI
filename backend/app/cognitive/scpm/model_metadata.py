"""
ModelMetadata — the serialisable form of a trained SCPM model.

We deliberately do NOT use pickle/joblib to serialise the sklearn object.
Reasons:
  1. Security: pickle is unsafe to deserialise from untrusted storage (Firestore).
  2. Auditability: plain float lists can be inspected directly in Firestore.
  3. Reproducibility: coefficients + scaler params fully define the model.

To reconstruct inference we keep:
  - coefficients (LR weight vector, shape [n_features])
  - intercept    (LR bias scalar)
  - scaler_mean_ / scaler_scale_ (StandardScaler parameters)

Everything else (feature_names, metrics, timestamps) is metadata only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ModelStatus(str, Enum):
    INSUFFICIENT_DATA = "insufficient_data"
    TRAINED = "trained"
    ACTIVE = "active"
    ERROR = "error"


SCPM_MODEL_VERSION = "SCPM-v1"


@dataclass
class ModelMetadata:
    user_id: str
    status: ModelStatus = ModelStatus.INSUFFICIENT_DATA
    model_version: str = SCPM_MODEL_VERSION

    # Training sample counts
    sample_count: int = 0
    positive_count: int = 0
    negative_count: int = 0

    # Evaluation metrics (None = not computed yet)
    accuracy: float | None = None
    baseline_accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    roc_auc: float | None = None

    # Model coefficients (empty = model not trained)
    coefficients: list[float] = field(default_factory=list)
    intercept: float = 0.0
    feature_names: list[str] = field(default_factory=list)

    # StandardScaler parameters (for inference reconstruction)
    scaler_mean: list[float] = field(default_factory=list)
    scaler_scale: list[float] = field(default_factory=list)

    # Timestamps
    trained_at: datetime | None = None
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Tracks how many new records since last training
    records_since_last_train: int = 0

    @property
    def is_active(self) -> bool:
        return self.status == ModelStatus.ACTIVE and bool(self.coefficients)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "status": self.status.value,
            "model_version": self.model_version,
            "sample_count": self.sample_count,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "accuracy": self.accuracy,
            "baseline_accuracy": self.baseline_accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "roc_auc": self.roc_auc,
            "coefficients": self.coefficients,
            "intercept": self.intercept,
            "feature_names": self.feature_names,
            "scaler_mean": self.scaler_mean,
            "scaler_scale": self.scaler_scale,
            "trained_at": self.trained_at,
            "last_updated": self.last_updated,
            "records_since_last_train": self.records_since_last_train,
        }

    @staticmethod
    def from_dict(user_id: str, data: dict | None) -> "ModelMetadata":
        if not data:
            return ModelMetadata(user_id=user_id)
        status_str = data.get("status", ModelStatus.INSUFFICIENT_DATA.value)
        try:
            status = ModelStatus(status_str)
        except ValueError:
            status = ModelStatus.INSUFFICIENT_DATA
        return ModelMetadata(
            user_id=user_id,
            status=status,
            model_version=data.get("model_version", SCPM_MODEL_VERSION),
            sample_count=data.get("sample_count", 0),
            positive_count=data.get("positive_count", 0),
            negative_count=data.get("negative_count", 0),
            accuracy=data.get("accuracy"),
            baseline_accuracy=data.get("baseline_accuracy"),
            precision=data.get("precision"),
            recall=data.get("recall"),
            f1=data.get("f1"),
            roc_auc=data.get("roc_auc"),
            coefficients=data.get("coefficients", []),
            intercept=data.get("intercept", 0.0),
            feature_names=data.get("feature_names", []),
            scaler_mean=data.get("scaler_mean", []),
            scaler_scale=data.get("scaler_scale", []),
            trained_at=data.get("trained_at"),
            last_updated=data.get("last_updated", datetime.now(timezone.utc)),
            records_since_last_train=data.get("records_since_last_train", 0),
        )

    def to_status_dict(self) -> dict[str, Any]:
        """Serialise for the public model-status API endpoint."""
        return {
            "active": self.is_active,
            "status": self.status.value,
            "model_version": self.model_version,
            "sample_count": self.sample_count,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "accuracy": round(self.accuracy, 4) if self.accuracy is not None else None,
            "baseline_accuracy": round(self.baseline_accuracy, 4) if self.baseline_accuracy is not None else None,
            "precision": round(self.precision, 4) if self.precision is not None else None,
            "recall": round(self.recall, 4) if self.recall is not None else None,
            "f1": round(self.f1, 4) if self.f1 is not None else None,
            "roc_auc": round(self.roc_auc, 4) if self.roc_auc is not None else None,
            "trained_at": self.trained_at.isoformat() if self.trained_at else None,
            "last_updated": self.last_updated.isoformat(),
            "records_since_last_train": self.records_since_last_train,
        }
