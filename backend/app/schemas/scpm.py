"""
Pydantic schemas for SCPM API endpoints.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class TrainRequest(BaseModel):
    """
    POST /personalization/train

    Triggers model training for the authenticated user.
    No body required — user_id comes from auth token.
    """
    force: bool = Field(
        default=False,
        description="If true, retrain even if records_since_last_train < threshold",
    )


class ModelStatusResponse(BaseModel):
    """GET /personalization/model-status"""
    active: bool
    status: str
    model_version: str
    sample_count: int
    positive_count: int
    negative_count: int
    accuracy: float | None
    baseline_accuracy: float | None
    precision: float | None
    recall: float | None
    f1: float | None
    roc_auc: float | None
    trained_at: str | None
    last_updated: str
    records_since_last_train: int
    message: str


class FeatureImportanceItem(BaseModel):
    feature: str
    coefficient: float
    interpretation: str


class ExplanationResponse(BaseModel):
    """GET /personalization/explanation"""
    model_active: bool
    model_version: str
    top_positive_factors: list[FeatureImportanceItem]
    top_negative_factors: list[FeatureImportanceItem]
    note: str


class TrainResponse(BaseModel):
    """POST /personalization/train response"""
    trained: bool
    status: str
    sample_count: int
    positive_count: int
    negative_count: int
    accuracy: float | None
    baseline_accuracy: float | None
    f1: float | None
    message: str
