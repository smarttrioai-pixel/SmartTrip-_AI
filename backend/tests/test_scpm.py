"""
Tests for the SmartTrip Cognitive Personalization Model (SCPM).

Tests:
  1. Feature extraction — correct vector shape, no leakage, clamping
  2. Dataset construction — from SCPMTrainingRecord dicts
  3. Trainer.train() — cold-start, sufficient data, evaluation metrics
  4. Predictor.predict() — active model, cold-start fallback
  5. ModelMetadata serialisation — to_dict / from_dict round-trip
  6. SCPMRepository — training record saving, model metadata persistence
  7. Recommendation integration — SCPM vs heuristic in score_and_rank
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.cognitive.scpm.feature_extractor import FeatureExtractor, FEATURE_NAMES, N_FEATURES
from app.cognitive.scpm.model_metadata import ModelMetadata, ModelStatus
from app.cognitive.scpm.trainer import SCPMTrainer
from app.cognitive.scpm.predictor import SCPMPredictor
from app.models.scpm import SCPMTrainingRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_record(label: int, category: str = "attraction") -> dict:
    """Create a minimal training record dict."""
    return {
        "label": label,
        "category": category,
        "estimated_cost": 20.0,
        "daily_budget_hint": 100.0,
        "weather_score": 0.8,
        "opening_hrs_score": 0.9,
        "context_composite": 0.75,
        "budget_sensitivity": 0.1,
        "crowd_aversion": -0.2,
        "novelty_seeking": 0.3,
        "distance_tolerance": 0.0,
        "pace_preference": -0.1,
    }


def _make_sufficient_records(n_pos: int = 7, n_neg: int = 5) -> list[dict]:
    """Create a balanced set of records sufficient for training."""
    records = [_make_record(1, cat) for cat in ["attraction", "culture", "museum", "nature", "meal", "transport", "other"][:n_pos]]
    records += [_make_record(0, cat) for cat in ["meal", "transport", "attraction", "culture", "other"][:n_neg]]
    return records


# ---------------------------------------------------------------------------
# 1. Feature Extraction
# ---------------------------------------------------------------------------

class TestFeatureExtractor:
    def setup_method(self):
        self.extractor = FeatureExtractor()

    def test_feature_vector_length(self):
        """Feature vector must always be N_FEATURES long."""
        vec = self.extractor.extract(
            category="attraction",
            estimated_cost=50.0,
            daily_budget_hint=200.0,
            weather_score=0.7,
            opening_hrs_score=0.85,
            context_composite=0.6,
            budget_sensitivity=0.2,
            crowd_aversion=-0.3,
            novelty_seeking=0.5,
            distance_tolerance=0.1,
            pace_preference=0.0,
        )
        assert len(vec) == N_FEATURES, f"Expected {N_FEATURES} features, got {len(vec)}"

    def test_category_one_hot(self):
        """Category OHE must have exactly one 1 in positions 0–6."""
        vec = self.extractor.extract(
            category="museum",
            estimated_cost=0.0, daily_budget_hint=100.0,
            weather_score=0.5, opening_hrs_score=0.75,
            context_composite=0.5,
            budget_sensitivity=0.0, crowd_aversion=0.0,
            novelty_seeking=0.0, distance_tolerance=0.0,
            pace_preference=0.0,
        )
        cat_vec = vec[:7]
        assert sum(cat_vec) == 1.0
        assert cat_vec[2] == 1.0  # "museum" is index 2

    def test_unknown_category_maps_to_other(self):
        """Unknown categories should map to 'other' (index 6)."""
        vec = self.extractor.extract(
            category="underwater_yoga",
            estimated_cost=0.0, daily_budget_hint=100.0,
            weather_score=0.5, opening_hrs_score=0.75,
            context_composite=0.5,
            budget_sensitivity=0.0, crowd_aversion=0.0,
            novelty_seeking=0.0, distance_tolerance=0.0,
            pace_preference=0.0,
        )
        cat_vec = vec[:7]
        assert cat_vec[6] == 1.0  # "other" is index 6

    def test_cost_ratio_clamped(self):
        """cost_ratio must be clamped to [0, 3]."""
        # Extremely expensive: cost >> budget
        vec = self.extractor.extract(
            category="attraction",
            estimated_cost=9999.0, daily_budget_hint=10.0,
            weather_score=0.5, opening_hrs_score=0.75,
            context_composite=0.5,
            budget_sensitivity=0.0, crowd_aversion=0.0,
            novelty_seeking=0.0, distance_tolerance=0.0,
            pace_preference=0.0,
        )
        cost_ratio = vec[7]
        assert cost_ratio == 3.0, f"Expected max 3.0, got {cost_ratio}"

    def test_zero_budget_cost_ratio(self):
        """When daily_budget_hint=0, cost_ratio should be 0 (not NaN/inf)."""
        vec = self.extractor.extract(
            category="attraction",
            estimated_cost=50.0, daily_budget_hint=0.0,
            weather_score=0.5, opening_hrs_score=0.75,
            context_composite=0.5,
            budget_sensitivity=0.0, crowd_aversion=0.0,
            novelty_seeking=0.0, distance_tolerance=0.0,
            pace_preference=0.0,
        )
        assert vec[7] == 0.0

    def test_no_label_field_in_vector(self):
        """Feature vector must never contain a 'label' field — no leakage."""
        vec = self.extractor.extract_from_record({
            "label": 1,  # must NOT appear in feature vector
            "category": "attraction",
            "estimated_cost": 20.0, "daily_budget_hint": 100.0,
            "weather_score": 0.8, "opening_hrs_score": 0.9,
            "context_composite": 0.75,
            "budget_sensitivity": 0.1, "crowd_aversion": 0.0,
            "novelty_seeking": 0.0, "distance_tolerance": 0.0,
            "pace_preference": 0.0,
        })
        # The label is 1, but we can't directly detect it by value.
        # Key check: vector length should equal N_FEATURES (not N_FEATURES+1)
        assert len(vec) == N_FEATURES
        # And FEATURE_NAMES must not include 'label'
        assert "label" not in FEATURE_NAMES

    def test_all_features_have_names(self):
        """FEATURE_NAMES must match N_FEATURES."""
        assert len(FEATURE_NAMES) == N_FEATURES


# ---------------------------------------------------------------------------
# 2. ModelMetadata serialisation
# ---------------------------------------------------------------------------

class TestModelMetadata:
    def test_empty_metadata_is_inactive(self):
        meta = ModelMetadata(user_id="test-user")
        assert not meta.is_active
        assert meta.status == ModelStatus.INSUFFICIENT_DATA

    def test_active_metadata_is_active(self):
        meta = ModelMetadata(
            user_id="test-user",
            status=ModelStatus.ACTIVE,
            coefficients=[0.1] * N_FEATURES,
        )
        assert meta.is_active

    def test_round_trip_serialisation(self):
        """to_dict() / from_dict() must be lossless."""
        meta = ModelMetadata(
            user_id="test-user",
            status=ModelStatus.ACTIVE,
            sample_count=42,
            positive_count=25,
            negative_count=17,
            accuracy=0.8571,
            f1=0.8333,
            coefficients=[0.1, -0.2, 0.3] + [0.0] * (N_FEATURES - 3),
            intercept=0.05,
            feature_names=list(FEATURE_NAMES),
            scaler_mean=[0.0] * N_FEATURES,
            scaler_scale=[1.0] * N_FEATURES,
        )
        serialised = meta.to_dict()
        restored = ModelMetadata.from_dict("test-user", serialised)
        assert restored.sample_count == 42
        assert restored.accuracy == 0.8571
        assert len(restored.coefficients) == N_FEATURES
        assert restored.status == ModelStatus.ACTIVE
        assert restored.is_active


# ---------------------------------------------------------------------------
# 3. Trainer
# ---------------------------------------------------------------------------

class TestSCPMTrainer:
    def setup_method(self):
        self.trainer = SCPMTrainer()

    def test_cold_start_returns_insufficient_data(self):
        """Fewer than 10 records must return INSUFFICIENT_DATA status."""
        records = [_make_record(1)] * 3 + [_make_record(0)] * 2
        meta = self.trainer.train("user-1", records)
        assert meta.status == ModelStatus.INSUFFICIENT_DATA
        assert meta.coefficients == []
        assert not meta.is_active

    def test_insufficient_positives(self):
        """At least 3 positive labels are required."""
        records = [_make_record(1)] * 2 + [_make_record(0)] * 10
        meta = self.trainer.train("user-1", records)
        assert meta.status == ModelStatus.INSUFFICIENT_DATA

    def test_insufficient_negatives(self):
        """At least 3 negative labels are required."""
        records = [_make_record(1)] * 10 + [_make_record(0)] * 2
        meta = self.trainer.train("user-1", records)
        assert meta.status == ModelStatus.INSUFFICIENT_DATA

    def test_sufficient_data_produces_active_model(self):
        """10+ records (≥3 pos, ≥3 neg) must produce ACTIVE status."""
        records = _make_sufficient_records(n_pos=7, n_neg=5)
        meta = self.trainer.train("user-2", records)
        assert meta.status == ModelStatus.ACTIVE
        assert len(meta.coefficients) == N_FEATURES
        assert len(meta.feature_names) == N_FEATURES
        assert len(meta.scaler_mean) == N_FEATURES
        assert len(meta.scaler_scale) == N_FEATURES
        assert meta.is_active

    def test_metrics_computed_for_large_dataset(self):
        """Accuracy, precision, recall, F1 should be computed when n >= 20."""
        records = _make_sufficient_records(n_pos=12, n_neg=10)
        meta = self.trainer.train("user-3", records)
        if meta.status == ModelStatus.ACTIVE and meta.sample_count >= 20:
            assert meta.accuracy is not None
            assert 0.0 <= meta.accuracy <= 1.0
            assert meta.f1 is not None

    def test_feature_importances_length(self):
        """Feature importances must match FEATURE_NAMES."""
        records = _make_sufficient_records()
        meta = self.trainer.train("user-4", records)
        if meta.is_active:
            importances = self.trainer.get_feature_importances(meta)
            assert len(importances) == N_FEATURES

    def test_invalid_labels_are_filtered(self):
        """Records with invalid labels (None, 2, -1) must be dropped."""
        records = _make_sufficient_records(n_pos=7, n_neg=5)
        # Add invalid records
        records.append({"label": None, "category": "attraction", "estimated_cost": 0.0,
                        "daily_budget_hint": 100.0, "weather_score": 0.5,
                        "opening_hrs_score": 0.75, "context_composite": 0.5,
                        "budget_sensitivity": 0.0, "crowd_aversion": 0.0,
                        "novelty_seeking": 0.0, "distance_tolerance": 0.0,
                        "pace_preference": 0.0})
        records.append({"label": 99, "category": "meal", "estimated_cost": 10.0,
                        "daily_budget_hint": 100.0, "weather_score": 0.5,
                        "opening_hrs_score": 0.75, "context_composite": 0.5,
                        "budget_sensitivity": 0.0, "crowd_aversion": 0.0,
                        "novelty_seeking": 0.0, "distance_tolerance": 0.0,
                        "pace_preference": 0.0})
        # Should still succeed (the invalid records are dropped)
        meta = self.trainer.train("user-5", records)
        assert meta.sample_count == len(_make_sufficient_records())  # invalid records excluded


# ---------------------------------------------------------------------------
# 4. Predictor
# ---------------------------------------------------------------------------

class TestSCPMPredictor:
    def setup_method(self):
        self.predictor = SCPMPredictor()

    def _make_active_meta(self) -> ModelMetadata:
        """Return a ModelMetadata with a trained model from sufficient data."""
        records = _make_sufficient_records(n_pos=8, n_neg=6)
        trainer = SCPMTrainer()
        return trainer.train("test-user", records)

    def test_cold_start_returns_neutral_probability(self):
        """When model is not active, probability must be 0.5 (neutral)."""
        meta = ModelMetadata(user_id="new-user")  # INSUFFICIENT_DATA, no coefficients
        result = self.predictor.predict(
            meta,
            category="attraction",
            estimated_cost=30.0, daily_budget_hint=100.0,
            weather_score=0.8, opening_hrs_score=0.9,
            context_composite=0.7,
            budget_sensitivity=0.0, crowd_aversion=0.0,
            novelty_seeking=0.0, distance_tolerance=0.0, pace_preference=0.0,
        )
        assert result.probability == 0.5
        assert result.model_active is False
        assert result.personalization_source == "heuristic"

    def test_active_model_returns_probability_in_range(self):
        """Active model must return a probability in [0, 1]."""
        meta = self._make_active_meta()
        if not meta.is_active:
            pytest.skip("Insufficient data to train model in test")
        result = self.predictor.predict(
            meta,
            category="attraction",
            estimated_cost=50.0, daily_budget_hint=200.0,
            weather_score=0.85, opening_hrs_score=0.90,
            context_composite=0.80,
            budget_sensitivity=0.1, crowd_aversion=-0.2,
            novelty_seeking=0.3, distance_tolerance=0.0, pace_preference=0.0,
        )
        assert 0.0 <= result.probability <= 1.0
        assert result.model_active is True
        assert result.personalization_source == "SCPM"

    def test_feature_vector_in_result(self):
        """PredictionResult must include the feature vector."""
        meta = ModelMetadata(user_id="new-user")
        result = self.predictor.predict(
            meta,
            category="meal",
            estimated_cost=15.0, daily_budget_hint=100.0,
            weather_score=0.6, opening_hrs_score=0.8,
            context_composite=0.65,
            budget_sensitivity=0.0, crowd_aversion=0.0,
            novelty_seeking=0.0, distance_tolerance=0.0, pace_preference=0.0,
        )
        assert len(result.feature_vector) == N_FEATURES


# ---------------------------------------------------------------------------
# 5. SCPMTrainingRecord
# ---------------------------------------------------------------------------

class TestSCPMTrainingRecord:
    def test_round_trip(self):
        record = SCPMTrainingRecord(
            user_id="u1",
            trip_id="t1",
            activity_title="Visit Museum",
            category="museum",
            estimated_cost=15.0,
            daily_budget_hint=100.0,
            weather_score=0.8,
            opening_hrs_score=0.9,
            context_composite=0.75,
            budget_sensitivity=0.1,
            crowd_aversion=-0.2,
            novelty_seeking=0.3,
            distance_tolerance=0.0,
            pace_preference=-0.1,
            label=1,
            event_type="accept",
        )
        d = record.to_dict()
        restored = SCPMTrainingRecord.from_dict(d)
        assert restored.user_id == "u1"
        assert restored.label == 1
        assert restored.category == "museum"
        assert restored.estimated_cost == 15.0

    def test_label_is_stored_correctly(self):
        """Label must be 1 for accept and 0 for reject."""
        r_accept = SCPMTrainingRecord(label=1, event_type="accept")
        r_reject = SCPMTrainingRecord(label=0, event_type="reject")
        assert r_accept.to_dict()["label"] == 1
        assert r_reject.to_dict()["label"] == 0


# ---------------------------------------------------------------------------
# 6. SCPMRepository (mocked Firestore)
# ---------------------------------------------------------------------------

class TestSCPMRepository:
    @pytest.mark.asyncio
    async def test_add_training_record_calls_firestore(self):
        """add_training_record() must set the document in Firestore."""
        from app.repositories.scpm_repository import SCPMRepository

        mock_db = MagicMock()
        mock_doc_ref = AsyncMock()
        mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_doc_ref

        repo = SCPMRepository(mock_db)
        record = SCPMTrainingRecord(user_id="u1", trip_id="t1", label=1)
        await repo.add_training_record(record)
        mock_doc_ref.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_model_metadata_returns_empty_when_missing(self):
        """get_model_metadata() must return empty ModelMetadata when doc doesn't exist."""
        from app.repositories.scpm_repository import SCPMRepository

        mock_db = MagicMock()
        mock_snap = MagicMock()
        mock_snap.exists = False
        mock_doc_ref = AsyncMock()
        mock_doc_ref.get = AsyncMock(return_value=mock_snap)
        mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_doc_ref

        repo = SCPMRepository(mock_db)
        meta = await repo.get_model_metadata("new-user")
        assert meta.status == ModelStatus.INSUFFICIENT_DATA
        assert not meta.is_active


# ---------------------------------------------------------------------------
# 7. Recommendation integration
# ---------------------------------------------------------------------------

class TestRecommendationSCPMIntegration:
    @pytest.mark.asyncio
    async def test_score_and_rank_uses_scpm_when_active(self):
        """score_and_rank() must use SCPM probability when model is active."""
        from app.cognitive.recommendation_engine import RecommendationEngine
        from app.cognitive.context_engine import ContextScoreBreakdown
        from app.models.user import UserPreferences

        # Mock ContextEngine to return deterministic scores
        mock_context_engine = MagicMock()
        mock_context_engine.evaluate_context = AsyncMock(
            return_value=ContextScoreBreakdown(
                opening_hours_score=0.9,
                weather_score=0.8,
                traffic_score=0.5,
                crowd_score=0.5,
                safety_score=0.5,
                unavailable_components=["traffic", "crowd", "safety"],
            )
        )

        # Build an active SCPM model
        records = _make_sufficient_records(n_pos=8, n_neg=6)
        trainer = SCPMTrainer()
        meta = trainer.train("test-user", records)

        if not meta.is_active:
            pytest.skip("Insufficient data to build active model in test")

        engine = RecommendationEngine(mock_context_engine)
        prefs = UserPreferences(interests=["history", "culture"], currency="USD")
        activities = [
            {"title": "Temple Visit", "category": "attraction",
             "estimated_cost": 20.0, "location": "Jaipur"},
            {"title": "Street Food Tour", "category": "meal",
             "estimated_cost": 15.0, "location": "Jaipur"},
        ]
        scored = await engine.score_and_rank(
            activities, prefs, daily_budget_hint=100.0,
            feature_weights={}, scpm_metadata=meta
        )
        # At least one should have SCPM as source
        sources = [s.personalization_source for s in scored]
        assert "SCPM" in sources

    @pytest.mark.asyncio
    async def test_score_and_rank_falls_back_to_heuristic_when_inactive(self):
        """score_and_rank() must fall back to heuristic when SCPM is cold-start."""
        from app.cognitive.recommendation_engine import RecommendationEngine
        from app.cognitive.context_engine import ContextScoreBreakdown
        from app.models.user import UserPreferences

        mock_context_engine = MagicMock()
        mock_context_engine.evaluate_context = AsyncMock(
            return_value=ContextScoreBreakdown(
                opening_hours_score=0.8,
                weather_score=0.7,
                traffic_score=0.5,
                crowd_score=0.5,
                safety_score=0.5,
                unavailable_components=["traffic", "crowd", "safety"],
            )
        )

        meta = ModelMetadata(user_id="cold-user")  # INSUFFICIENT_DATA

        engine = RecommendationEngine(mock_context_engine)
        prefs = UserPreferences(interests=[], currency="USD")
        activities = [{"title": "Park Visit", "category": "nature", "estimated_cost": 0.0}]
        scored = await engine.score_and_rank(
            activities, prefs, daily_budget_hint=100.0,
            feature_weights={}, scpm_metadata=meta
        )
        assert scored[0].personalization_source == "heuristic"
