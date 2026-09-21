"""
SCPMRepository — Firestore persistence layer for SCPM.

Collections:
  scpm_training_records/{user_id}/records/{record_id}
    → labelled feedback events (training data)

  users/{user_id}/personalization_model   (single document per user)
    → trained model metadata (coefficients, metrics, etc.)

Design:
  - Training records are append-only (never updated/deleted).
  - Model metadata is overwritten on each training run (set, not update).
  - All Firestore access is async via google-cloud-firestore AsyncClient.
"""
from __future__ import annotations

import logging
from typing import Any

from google.cloud.firestore import AsyncClient

from app.cognitive.scpm.model_metadata import ModelMetadata
from app.models.scpm import SCPMTrainingRecord

logger = logging.getLogger(__name__)

SCPM_RECORDS_COLLECTION = "scpm_training_records"
USERS_COLLECTION = "users"
MODEL_DOCUMENT = "personalization_model"


class SCPMRepository:
    def __init__(self, db: AsyncClient) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Training records
    # ------------------------------------------------------------------

    async def add_training_record(self, record: SCPMTrainingRecord) -> None:
        """Append one labelled training record to Firestore (async, fire-and-forget safe)."""
        try:
            doc_ref = (
                self._db
                .collection(SCPM_RECORDS_COLLECTION)
                .document(record.user_id)
                .collection("records")
                .document(record.id)
            )
            await doc_ref.set(record.to_dict())
            logger.debug("SCPM_RECORD_SAVED user=%s record=%s label=%d",
                         record.user_id, record.id, record.label)
        except Exception as exc:
            # Training record failures must not crash the feedback endpoint
            logger.error("SCPM_RECORD_ERROR user=%s error=%s", record.user_id, exc)

    async def get_training_records(self, user_id: str, limit: int = 500) -> list[dict[str, Any]]:
        """Retrieve all training records for a user (up to limit)."""
        try:
            col = (
                self._db
                .collection(SCPM_RECORDS_COLLECTION)
                .document(user_id)
                .collection("records")
                .limit(limit)
            )
            records: list[dict] = []
            async for snap in col.stream():
                records.append(snap.to_dict())
            logger.debug("SCPM_RECORDS_LOADED user=%s count=%d", user_id, len(records))
            return records
        except Exception as exc:
            logger.error("SCPM_RECORDS_LOAD_ERROR user=%s error=%s", user_id, exc)
            return []

    async def count_training_records(self, user_id: str) -> tuple[int, int, int]:
        """
        Returns (total, positive_count, negative_count) from training records.
        Efficient for cold-start checks without loading full records.
        """
        records = await self.get_training_records(user_id, limit=500)
        total = len(records)
        pos = sum(1 for r in records if r.get("label") == 1)
        neg = total - pos
        return total, pos, neg

    # ------------------------------------------------------------------
    # Model metadata
    # ------------------------------------------------------------------

    async def save_model_metadata(self, meta: ModelMetadata) -> None:
        """Persist trained model metadata to users/{uid}/personalization_model."""
        try:
            doc_ref = (
                self._db
                .collection(USERS_COLLECTION)
                .document(meta.user_id)
                .collection("personalization_model")
                .document("current")
            )
            await doc_ref.set(meta.to_dict())
            logger.info("SCPM_META_SAVED user=%s status=%s", meta.user_id, meta.status.value)
        except Exception as exc:
            logger.error("SCPM_META_SAVE_ERROR user=%s error=%s", meta.user_id, exc)
            raise

    async def get_model_metadata(self, user_id: str) -> ModelMetadata:
        """Load model metadata for a user. Returns empty/inactive metadata if not found."""
        try:
            doc_ref = (
                self._db
                .collection(USERS_COLLECTION)
                .document(user_id)
                .collection("personalization_model")
                .document("current")
            )
            snap = await doc_ref.get()
            if snap.exists:
                return ModelMetadata.from_dict(user_id, snap.to_dict())
        except Exception as exc:
            logger.error("SCPM_META_LOAD_ERROR user=%s error=%s", user_id, exc)
        return ModelMetadata(user_id=user_id)

    async def increment_records_since_train(self, user_id: str) -> int:
        """
        Atomically increment the records_since_last_train counter.
        Returns the new count. Used to trigger retraining.
        """
        meta = await self.get_model_metadata(user_id)
        meta.records_since_last_train += 1
        await self.save_model_metadata(meta)
        return meta.records_since_last_train
