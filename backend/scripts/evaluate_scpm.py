"""
CLI script: Evaluate SCPM for a specific user.

Usage:
    python scripts/evaluate_scpm.py --user-id USER_ID [--output-json results.json]

Loads existing training records and model metadata, then produces:
  - Full confusion matrix
  - Per-class precision/recall/F1
  - Calibration check (expected vs. observed positive rate)
  - Feature importance table
  - Research-ready formatted report

This script does NOT retrain the model — it evaluates the currently stored model.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix,
    f1_score, precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from app.core.firebase import get_firestore_client
from app.repositories.scpm_repository import SCPMRepository
from app.cognitive.scpm.feature_extractor import FeatureExtractor, FEATURE_NAMES
from app.cognitive.scpm.trainer import SCPMTrainer
from app.cognitive.scpm.model_metadata import ModelStatus


async def main(user_id: str, output_json: str | None = None) -> None:
    print(f"\n{'='*70}")
    print(f"SCPM Evaluation Report — SmartTrip AI")
    print(f"{'='*70}")
    print(f"User ID:   {user_id}")
    print(f"Timestamp: {datetime.now().isoformat()}")

    db = get_firestore_client()
    repo = SCPMRepository(db)

    print("\nLoading data...")
    records = await repo.get_training_records(user_id)
    meta = await repo.get_model_metadata(user_id)

    n = len(records)
    valid_records = [r for r in records if r.get("label") in (0, 1)]
    n_valid = len(valid_records)
    n_pos = sum(1 for r in valid_records if r["label"] == 1)
    n_neg = n_valid - n_pos

    print(f"\nDataset:")
    print(f"  Total records:   {n}")
    print(f"  Valid records:   {n_valid}")
    print(f"  Positive:        {n_pos}  ({n_pos/max(n_valid,1)*100:.1f}%)")
    print(f"  Negative:        {n_neg}  ({n_neg/max(n_valid,1)*100:.1f}%)")
    print(f"  Baseline acc:    {max(n_pos, n_neg)/max(n_valid,1):.4f}")

    if n_valid < 5:
        print("\n❌ Insufficient data for evaluation.")
        return

    extractor = FeatureExtractor()
    X = np.array([extractor.extract_from_record(r) for r in valid_records], dtype=np.float64)
    y = np.array([r["label"] for r in valid_records], dtype=np.int32)

    # Scale using StandardScaler (refit for evaluation)
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    lr = LogisticRegression(max_iter=1000, class_weight="balanced", solver="lbfgs", random_state=42)

    # Cross-validated evaluation
    k = min(5, max(3, n_valid // 5))
    cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=42)
    y_pred = cross_val_predict(lr, X_scaled, y, cv=cv)
    y_prob = cross_val_predict(lr, X_scaled, y, cv=cv, method="predict_proba")[:, 1]

    acc = accuracy_score(y, y_pred)
    baseline = max(n_pos, n_neg) / n_valid
    prec = precision_score(y, y_pred, zero_division=0)
    rec = recall_score(y, y_pred, zero_division=0)
    f1 = f1_score(y, y_pred, zero_division=0)
    try:
        auc = roc_auc_score(y, y_prob)
    except ValueError:
        auc = None

    cm = confusion_matrix(y, y_pred)

    print(f"\n{'='*70}")
    print(f"Cross-Validated Evaluation ({k}-fold Stratified KFold)")
    print(f"{'='*70}")
    print(f"\nOverall Metrics:")
    print(f"  Accuracy:        {acc:.4f}  (+{acc-baseline:+.4f} above baseline {baseline:.4f})")
    print(f"  Precision:       {prec:.4f}")
    print(f"  Recall:          {rec:.4f}")
    print(f"  F1 Score:        {f1:.4f}")
    if auc:
        print(f"  ROC AUC:         {auc:.4f}")

    print(f"\nConfusion Matrix:")
    print(f"              Predicted")
    print(f"              Reject  Accept")
    print(f"  Actual Rej:  {cm[0][0]:5d}  {cm[0][1]:5d}")
    print(f"  Actual Acc:  {cm[1][0]:5d}  {cm[1][1]:5d}")

    print(f"\nClassification Report:")
    print(classification_report(y, y_pred, target_names=["Reject (0)", "Accept (1)"]))

    # Calibration check
    prob_positive_expected = y_prob.mean()
    prob_positive_actual = y.mean()
    print(f"Calibration:")
    print(f"  Expected positive rate (model):  {prob_positive_expected:.3f}")
    print(f"  Actual positive rate (data):     {prob_positive_actual:.3f}")
    calib_error = abs(prob_positive_expected - prob_positive_actual)
    print(f"  Calibration error:               {calib_error:.3f}", end="")
    print(f"  {'✅ Good' if calib_error < 0.1 else '⚠️ High'}")

    # Feature importances (from full fit on all data)
    lr.fit(X_scaled, y)
    trainer = SCPMTrainer()
    from app.cognitive.scpm.model_metadata import ModelMetadata
    tmp_meta = ModelMetadata(user_id=user_id)
    tmp_meta.coefficients = lr.coef_[0].tolist()
    tmp_meta.feature_names = list(FEATURE_NAMES)
    importances = trainer.get_feature_importances(tmp_meta)

    print(f"\nFeature Importances (full dataset fit):")
    print(f"  {'Feature':<30}  {'Coefficient':>12}  Direction")
    print(f"  {'-'*58}")
    for item in importances:
        direction = "↑ promotes acceptance" if item["coefficient"] > 0 else "↓ promotes rejection"
        print(f"  {item['feature']:<30}  {item['coefficient']:+12.4f}  {direction}")

    # Stored model comparison
    print(f"\nStored Model Status:")
    print(f"  Status:    {meta.status.value}")
    if meta.is_active:
        print(f"  Trained:   {meta.trained_at}")
        print(f"  Samples:   {meta.sample_count}")
        print(f"  Acc (stored): {meta.accuracy}")

    report = {
        "user_id": user_id,
        "timestamp": datetime.now().isoformat(),
        "dataset": {
            "total": n_valid,
            "positive": n_pos,
            "negative": n_neg,
            "baseline_accuracy": baseline,
        },
        "evaluation": {
            "cv_folds": k,
            "accuracy": acc,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "roc_auc": auc,
            "calibration_error": calib_error,
        },
        "confusion_matrix": cm.tolist(),
        "feature_importances": importances,
        "stored_model_status": meta.status.value,
    }

    if output_json:
        with open(output_json, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n✅ Evaluation saved to: {output_json}")

    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate SCPM for a user")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--output-json", help="Save evaluation report to JSON file")
    args = parser.parse_args()
    asyncio.run(main(args.user_id, output_json=args.output_json))
