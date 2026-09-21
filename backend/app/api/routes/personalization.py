"""
Personalization API routes for SmartTrip AI (SCPM).

Endpoints:
  POST /personalization/train          — trigger model training for current user
  GET  /personalization/model-status   — training metadata, sample counts, metrics
  GET  /personalization/explanation    — feature coefficients (what drives recommendations)
  POST /personalization/debug          — per-activity SCPM probability (for development)

Design:
  - Training is triggered manually (this endpoint) or automatically when
    MemoryEngine accumulates SCPM_RETRAIN_THRESHOLD new feedback records.
  - All metrics reported are real (computed by SCPMTrainer on actual data).
  - The model is only marked ACTIVE when training succeeds.
  - Cold-start case: returns model_active=False, not an error.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, get_scpm_repository
from app.cognitive.scpm.model_metadata import ModelStatus
from app.cognitive.scpm.trainer import SCPMTrainer
from app.repositories.scpm_repository import SCPMRepository
from app.schemas.scpm import (
    ExplanationResponse,
    FeatureImportanceItem,
    ModelStatusResponse,
    TrainRequest,
    TrainResponse,
)

router = APIRouter(prefix="/personalization", tags=["Personalization"])
logger = logging.getLogger(__name__)

_FEATURE_INTERPRETATIONS: dict[str, str] = {
    "cat_attraction": "Tourist attractions / landmarks",
    "cat_culture": "Cultural experiences",
    "cat_museum": "Museums",
    "cat_nature": "Nature / outdoor activities",
    "cat_meal": "Dining / restaurants",
    "cat_transport": "Transport activities",
    "cat_other": "Other activity types",
    "cost_ratio": "Activity cost relative to daily budget",
    "weather_score": "Weather suitability at time of activity",
    "opening_hrs_score": "Whether place is open during visit time",
    "context_composite": "Overall context suitability score",
    "budget_sensitivity": "Your sensitivity to activity costs",
    "crowd_aversion": "Your preference for less crowded places",
    "novelty_seeking": "Your preference for new/unique experiences",
    "distance_tolerance": "Your willingness to travel further",
    "pace_preference": "Your preferred travel pace",
}


@router.post(
    "/train",
    response_model=TrainResponse,
    summary="Train or retrain the personalization model for the current user",
    description=(
        "Triggers Logistic Regression training on all feedback records collected "
        "for the authenticated user. Returns training results including sample counts "
        "and evaluation metrics. Model is only marked active if training succeeds and "
        "cold-start thresholds are met (≥10 total, ≥3 positive, ≥3 negative)."
    ),
)
async def train_model(
    payload: TrainRequest,
    current_user: CurrentUser,
    scpm_repo: Annotated[SCPMRepository, Depends(get_scpm_repository)],
) -> TrainResponse:
    """Train SCPM for the current user."""
    logger.info("SCPM_TRAIN_REQUEST user=%s force=%s", current_user.id, payload.force)

    try:
        records = await scpm_repo.get_training_records(current_user.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to load training records: {exc}",
        ) from exc

    n = len(records)
    trainer = SCPMTrainer()

    if n == 0:
        meta = await scpm_repo.get_model_metadata(current_user.id)
        return TrainResponse(
            trained=False,
            status=ModelStatus.INSUFFICIENT_DATA.value,
            sample_count=0,
            positive_count=0,
            negative_count=0,
            accuracy=None,
            baseline_accuracy=None,
            f1=None,
            message=(
                "No training records found. Submit activity feedback via "
                "POST /memory/feedback to generate training data."
            ),
        )

    try:
        meta = trainer.train(current_user.id, records)
    except Exception as exc:
        logger.error("SCPM_TRAIN_FAIL user=%s error=%s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Training failed: {exc}",
        ) from exc

    try:
        await scpm_repo.save_model_metadata(meta)
    except Exception as exc:
        logger.error("SCPM_META_SAVE_FAIL user=%s error=%s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Training succeeded but failed to save model: {exc}",
        ) from exc

    logger.info(
        "SCPM_TRAINED user=%s samples=%d pos=%d neg=%d acc=%s f1=%s",
        current_user.id, meta.sample_count, meta.positive_count,
        meta.negative_count, meta.accuracy, meta.f1,
    )

    if meta.status == ModelStatus.ACTIVE:
        msg = (
            f"Model trained successfully on {meta.sample_count} samples. "
            f"Accuracy: {meta.accuracy:.3f} (baseline: {meta.baseline_accuracy:.3f}). "
            f"SCPM is now active and will influence recommendations."
        )
    else:
        msg = (
            f"Insufficient data for training. Need ≥10 total, ≥3 positive, ≥3 negative. "
            f"Currently: {meta.sample_count} total, "
            f"{meta.positive_count} positive, {meta.negative_count} negative."
        )

    return TrainResponse(
        trained=meta.status == ModelStatus.ACTIVE,
        status=meta.status.value,
        sample_count=meta.sample_count,
        positive_count=meta.positive_count,
        negative_count=meta.negative_count,
        accuracy=meta.accuracy,
        baseline_accuracy=meta.baseline_accuracy,
        f1=meta.f1,
        message=msg,
    )


@router.get(
    "/model-status",
    response_model=ModelStatusResponse,
    summary="Get SCPM model status and evaluation metrics",
)
async def get_model_status(
    current_user: CurrentUser,
    scpm_repo: Annotated[SCPMRepository, Depends(get_scpm_repository)],
) -> ModelStatusResponse:
    """Return the current SCPM model status for the authenticated user."""
    meta = await scpm_repo.get_model_metadata(current_user.id)

    if meta.status == ModelStatus.ACTIVE:
        message = (
            f"SCPM is active. Using trained ML model for personalization. "
            f"Trained on {meta.sample_count} feedback events. "
            f"Accuracy: {meta.accuracy:.3f} (baseline: {meta.baseline_accuracy:.3f})."
        )
    elif meta.status == ModelStatus.INSUFFICIENT_DATA:
        total, pos, neg = await scpm_repo.count_training_records(current_user.id)
        message = (
            f"SCPM not yet active (cold-start). "
            f"Current data: {total} records ({pos} positive, {neg} negative). "
            f"Need: ≥10 total, ≥3 positive, ≥3 negative. "
            f"Submit more feedback via POST /memory/feedback."
        )
    else:
        message = f"Model status: {meta.status.value}."

    return ModelStatusResponse(
        **meta.to_status_dict(),
        message=message,
    )


@router.get(
    "/explanation",
    response_model=ExplanationResponse,
    summary="Get SCPM feature importances (what drives your recommendations)",
)
async def get_explanation(
    current_user: CurrentUser,
    scpm_repo: Annotated[SCPMRepository, Depends(get_scpm_repository)],
) -> ExplanationResponse:
    """
    Return SCPM feature coefficients, split into positive (factors that
    increase recommendation probability) and negative (factors that decrease it).
    """
    meta = await scpm_repo.get_model_metadata(current_user.id)

    if not meta.is_active:
        return ExplanationResponse(
            model_active=False,
            model_version=meta.model_version,
            top_positive_factors=[],
            top_negative_factors=[],
            note=(
                "SCPM model is not yet active. "
                "Train the model with sufficient feedback data first."
            ),
        )

    trainer = SCPMTrainer()
    importances = trainer.get_feature_importances(meta)

    positive = [
        FeatureImportanceItem(
            feature=item["feature"],
            coefficient=item["coefficient"],
            interpretation=_FEATURE_INTERPRETATIONS.get(item["feature"], item["feature"]),
        )
        for item in importances if item["coefficient"] > 0
    ][:8]

    negative = [
        FeatureImportanceItem(
            feature=item["feature"],
            coefficient=item["coefficient"],
            interpretation=_FEATURE_INTERPRETATIONS.get(item["feature"], item["feature"]),
        )
        for item in importances if item["coefficient"] < 0
    ][:8]

    return ExplanationResponse(
        model_active=True,
        model_version=meta.model_version,
        top_positive_factors=positive,
        top_negative_factors=negative,
        note=(
            f"Coefficients represent log-odds (positive = more likely to accept). "
            f"Trained on {meta.sample_count} feedback events. "
            f"Model accuracy: {meta.accuracy:.3f}."
        ),
    )
