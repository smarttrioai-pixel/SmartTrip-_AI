"""
CLI script: Train SCPM for a specific user.

Usage:
    python scripts/train_scpm.py --user-id USER_ID [--force]

This script loads training records from Firestore, trains the SCPM
Logistic Regression model, saves the model metadata, and prints
a detailed evaluation report.

Requirements:
    - GOOGLE_APPLICATION_CREDENTIALS or Firebase credentials in environment
    - FIREBASE_PROJECT_ID env var
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.firebase import get_firestore_client
from app.repositories.scpm_repository import SCPMRepository
from app.cognitive.scpm.trainer import SCPMTrainer
from app.cognitive.scpm.model_metadata import ModelStatus


async def main(user_id: str, force: bool = False) -> None:
    print(f"\n{'='*60}")
    print(f"SCPM Training Script — SmartTrip AI")
    print(f"{'='*60}")
    print(f"User ID: {user_id}")
    print(f"Force:   {force}")
    print()

    db = get_firestore_client()
    repo = SCPMRepository(db)

    print("Loading training records from Firestore...")
    records = await repo.get_training_records(user_id)
    n = len(records)
    n_pos = sum(1 for r in records if r.get("label") == 1)
    n_neg = n - n_pos

    print(f"  Total records:   {n}")
    print(f"  Positive labels: {n_pos}  (user accepted)")
    print(f"  Negative labels: {n_neg}  (user rejected)")

    if n == 0:
        print("\n❌ No training records found.")
        print("   Submit feedback via POST /memory/feedback to generate training data.")
        return

    if not force and n < 10:
        print(f"\n⚠️  Only {n} records. Minimum is 10.")
        print("   Use --force to attempt training anyway.")

    print("\nTraining SCPM model...")
    trainer = SCPMTrainer()
    meta = trainer.train(user_id, records)

    print(f"\n{'='*60}")
    print(f"Training Results")
    print(f"{'='*60}")
    print(f"Status:          {meta.status.value}")
    print(f"Samples used:    {meta.sample_count}")
    print(f"Positive:        {meta.positive_count}")
    print(f"Negative:        {meta.negative_count}")

    if meta.accuracy is not None:
        print(f"\nEvaluation Metrics:")
        print(f"  Accuracy:        {meta.accuracy:.4f}  (baseline: {meta.baseline_accuracy:.4f})")
        print(f"  Precision:       {meta.precision:.4f}")
        print(f"  Recall:          {meta.recall:.4f}")
        print(f"  F1 Score:        {meta.f1:.4f}")
        if meta.roc_auc is not None:
            print(f"  ROC AUC:         {meta.roc_auc:.4f}")
    else:
        print(f"\n⚠️  Insufficient data for split-based evaluation.")
        print(f"   Baseline accuracy: {meta.baseline_accuracy:.4f}")

    if meta.coefficients:
        print(f"\nTop Feature Importances (by |coefficient|):")
        importances = trainer.get_feature_importances(meta)
        for i, item in enumerate(importances[:10], 1):
            bar = "+" if item["coefficient"] > 0 else ""
            print(f"  {i:2d}. {item['feature']:30s}  {bar}{item['coefficient']:+.4f}")

    if meta.status == ModelStatus.ACTIVE:
        print("\n✅ Saving model to Firestore...")
        await repo.save_model_metadata(meta)
        print("✅ Model saved. SCPM is now ACTIVE.")
        print("   Next trip generation will use ML-based personalization.")
    else:
        print("\n❌ Model not saved — insufficient data for training.")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train SCPM for a user")
    parser.add_argument("--user-id", required=True, help="Firebase user ID")
    parser.add_argument("--force", action="store_true", help="Force training even if below threshold")
    args = parser.parse_args()
    asyncio.run(main(args.user_id, force=args.force))
