"""
SCPM (SmartTrip Cognitive Personalization Model) package.

A trainable Logistic Regression model that learns user activity preferences
from real feedback interactions. Separate from and complementary to the LLM.

Architecture:
    User feedback (accept/reject)
        ↓
    SCPMTrainingRecord (features + label) → Firestore
        ↓ (when threshold met)
    SCPMTrainer.train() → LogisticRegression
        ↓
    ModelMetadata (coefficients) → Firestore
        ↓
    SCPMPredictor.predict() → P(user accepts activity)
        ↓
    RecommendationEngine.personalization_score
"""
from app.cognitive.scpm.model_metadata import ModelMetadata, ModelStatus
from app.cognitive.scpm.feature_extractor import FeatureExtractor, FEATURE_NAMES
from app.cognitive.scpm.trainer import SCPMTrainer
from app.cognitive.scpm.predictor import SCPMPredictor

__all__ = [
    "ModelMetadata",
    "ModelStatus",
    "FeatureExtractor",
    "FEATURE_NAMES",
    "SCPMTrainer",
    "SCPMPredictor",
]
