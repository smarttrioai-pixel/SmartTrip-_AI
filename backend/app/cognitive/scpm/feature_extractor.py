"""
Feature extractor for SCPM.

Converts (activity_dict, behavioral_weights, context_score_breakdown)
into a fixed-length numeric feature vector suitable for Logistic Regression.

IMPORTANT — no data-leakage design:
  - The label (accept=1 / reject=0) is NEVER part of this feature vector.
  - This function only reads activity properties, behavioral weights, and
    context scores — all of which are known BEFORE the user gives feedback.

Feature vector (16 dimensions):
  [0-6]  Category one-hot: attraction, culture, museum, nature,
                            meal, transport, other
  [7]    cost_ratio         = estimated_cost / daily_budget_hint (clamped [0,3])
  [8]    weather_score      = ContextEngine weather (0.0–1.0)
  [9]    opening_hrs_score  = ContextEngine opening hours (0.0–1.0)
  [10]   context_composite  = ContextEngine composite (0.0–1.0)
  [11]   budget_sensitivity = user behavioral weight (–1.0 to 1.0)
  [12]   crowd_aversion     = user behavioral weight (–1.0 to 1.0)
  [13]   novelty_seeking    = user behavioral weight (–1.0 to 1.0)
  [14]   distance_tolerance = user behavioral weight (–1.0 to 1.0)
  [15]   pace_preference    = user behavioral weight (–1.0 to 1.0)
"""
from __future__ import annotations

CATEGORIES = ["attraction", "culture", "museum", "nature", "meal", "transport", "other"]

FEATURE_NAMES: list[str] = (
    [f"cat_{c}" for c in CATEGORIES]
    + ["cost_ratio", "weather_score", "opening_hrs_score", "context_composite"]
    + ["budget_sensitivity", "crowd_aversion", "novelty_seeking",
       "distance_tolerance", "pace_preference"]
)

N_FEATURES = len(FEATURE_NAMES)  # 16


class FeatureExtractor:
    """
    Stateless feature extractor.  All inputs must be available before the
    user provides feedback (guaranteed by design — see data flow in SCPM_DESIGN.md).
    """

    def extract(
        self,
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
    ) -> list[float]:
        """
        Return a 16-element feature vector.

        All floats outside expected ranges are clamped to prevent model instability.
        Missing/unknown values use neutral defaults (0.5 for scores, 0.0 for weights).
        """
        # Category one-hot (7 dims)
        cat = (category or "other").lower().strip()
        if cat not in CATEGORIES:
            cat = "other"
        cat_ohe = [1.0 if cat == c else 0.0 for c in CATEGORIES]

        # Cost ratio — clamped to [0, 3] so extreme outliers don't destabilise LR
        if daily_budget_hint > 0:
            cost_ratio = min(3.0, max(0.0, estimated_cost / daily_budget_hint))
        else:
            cost_ratio = 0.0

        # Context scores — clamped [0, 1]
        weather = _clamp01(weather_score)
        opening = _clamp01(opening_hrs_score)
        ctx = _clamp01(context_composite)

        # Behavioral weights — clamped [–1, 1]
        b_sens = _clamp11(budget_sensitivity)
        c_aver = _clamp11(crowd_aversion)
        n_seek = _clamp11(novelty_seeking)
        d_tol = _clamp11(distance_tolerance)
        p_pref = _clamp11(pace_preference)

        return cat_ohe + [cost_ratio, weather, opening, ctx,
                          b_sens, c_aver, n_seek, d_tol, p_pref]

    def extract_from_record(self, record: dict) -> list[float]:
        """
        Convenience method: extract features from a SCPMTrainingRecord dict.
        """
        return self.extract(
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


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v) if v is not None else 0.5))


def _clamp11(v: float) -> float:
    return max(-1.0, min(1.0, float(v) if v is not None else 0.0))
