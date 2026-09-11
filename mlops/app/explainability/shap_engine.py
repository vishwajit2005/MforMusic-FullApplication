"""
shap_engine.py — Phase 3 of the MforMusic Explainability Pipeline
==================================================================
Uses the trained XGBoost surrogate to compute SHAP explanations:
  - Global importance (mean |SHAP|) → global_importance.json
  - Per-(user, song) SHAP values    → explain_one() (called at API request time)
  - Feature metadata                → feature_metadata.json (UI labels)

Also saves the TreeExplainer as shap_explainer.joblib so the API module
can load it once at startup and call explain_one() cheaply per request.

Usage (run after train_surrogate.py):
    cd mlops/
    python -m app.explainability.shap_engine

Artifacts produced (in app/explainability/artifacts/):
    shap_explainer.joblib    — pickled TreeExplainer
    global_importance.json   — {feature: mean_abs_shap_value, ...}
    feature_metadata.json    — {feature: {label, description}, ...}
"""

import json
import logging
import sys
from pathlib import Path

import joblib
import pandas as pd

try:
    import shap
except ImportError:
    print("ERROR: shap not installed. Run: pip install shap")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

DATASET_PATH = BASE_DIR / "dataset" / "explainability_training_data.parquet"
MODEL_PATH = ARTIFACTS_DIR / "surrogate_model.joblib"
FEATURES_PATH = ARTIFACTS_DIR / "feature_list.joblib"

EXPLAINER_PATH = ARTIFACTS_DIR / "shap_explainer.joblib"
GLOBAL_IMPORTANCE_PATH = ARTIFACTS_DIR / "global_importance.json"
FEATURE_METADATA_PATH = ARTIFACTS_DIR / "feature_metadata.json"

# ── Human-readable feature metadata ──────────────────────────────────────────
# This dict is the single source of truth for UI labels.
FEATURE_METADATA = {
    "likes_count": {
        "label": "Song Popularity (Likes)",
        "description": "Total likes this song has received across all users",
    },
    "user_play_count": {
        "label": "Your Play History",
        "description": "How many times you have played this song before",
    },
    "skip_count": {
        "label": "Your Skip History",
        "description": "How many times you have skipped this song (negative signal)",
    },
    "completion_rate": {
        "label": "Average Listen Completion",
        "description": "Average fraction of the song you listen to (0–1)",
    },
    "genre_language_match": {
        "label": "Language Match",
        "description": "1 if this song's language matches your most-listened language",
    },
    "decade_match": {
        "label": "Era Match",
        "description": "1 if this song's decade matches your preferred music era",
    },
    "content_similarity_score": {
        "label": "Audio Similarity",
        "description": (
            "Cosine similarity to the seed song used for content-based recommendations "
            "(0 if not a content-based rec, or 0 for all historical rows where "
            "the serving tier was not logged — see README.md)."
        ),
    },
    "popularity_score": {
        "label": "Global Popularity",
        "description": "Log-normalized global play count of this song across all users",
    },
    "recency_days": {
        "label": "Days Since You Last Listened",
        "description": "How many days have passed since your last interaction with this song (higher = older)",
    },
    "tier_used_collaborative_filtering": {
        "label": "Recommended by: Collaborative Filtering",
        "description": "This recommendation came from the ALS collaborative filtering model",
    },
    "tier_used_content_based": {
        "label": "Recommended by: Audio Similarity",
        "description": "This recommendation came from the content-based similarity model",
    },
    "tier_used_popular": {
        "label": "Recommended by: Popularity",
        "description": "This recommendation came from the popular songs fallback",
    },
    "tier_used_unknown": {
        "label": "Tier: Not Logged (Historical)",
        "description": (
            "The recommendation-serving tier was not logged for this historical interaction. "
            "All rows in the initial training dataset have this value. "
            "Once recommendation-serving events are logged, this field will be replaced "
            "by the actual tier (see README.md — Future Improvement)."
        ),
    },
}


def build_explainer() -> None:
    """
    Main entry point: loads the surrogate model + dataset,
    computes global SHAP values, and saves all artifacts.
    """
    logger.info("=== MforMusic SHAP Engine ===")

    # ── Load artifacts ────────────────────────────────────────────────────────
    for path, name in [(MODEL_PATH, "surrogate_model"), (FEATURES_PATH, "feature_list"), (DATASET_PATH, "dataset")]:
        if not path.exists():
            logger.error(f"{name} not found at {path}. Run the preceding pipeline steps first.")
            sys.exit(1)

    model = joblib.load(MODEL_PATH)
    FEATURES = joblib.load(FEATURES_PATH)
    logger.info(f"Loaded model with {len(FEATURES)} features.")

    # ── Load dataset and apply the same one-hot encoding as training ──────────
    df = pd.read_parquet(DATASET_PATH)
    df = pd.get_dummies(df, columns=["tier_used"], prefix="tier_used")

    # Must match TIER_DUMMIES in train_surrogate.py exactly.
    # "unknown" is the dominant category for all historical training rows.
    tier_dummies = [
        "tier_used_collaborative_filtering",
        "tier_used_content_based",
        "tier_used_popular",
        "tier_used_unknown",   # ← ALL historical rows until serving-event logging is added
    ]
    for col in tier_dummies:
        if col not in df.columns:
            df[col] = 0

    X = df[FEATURES].copy()
    logger.info(f"Computing SHAP values for {len(X):,} rows...")

    # ── Build TreeExplainer ───────────────────────────────────────────────────
    explainer = shap.TreeExplainer(model)
    joblib.dump(explainer, EXPLAINER_PATH)
    logger.info(f"Saved SHAP explainer → {EXPLAINER_PATH}")

    # ── Global importance: mean |SHAP value| per feature ─────────────────────
    shap_values = explainer.shap_values(X)
    importance_series = (
        pd.DataFrame(shap_values, columns=FEATURES)
        .abs()
        .mean()
        .sort_values(ascending=False)
    )
    global_importance = {k: round(float(v), 6) for k, v in importance_series.items()}

    with open(GLOBAL_IMPORTANCE_PATH, "w") as f:
        json.dump(global_importance, f, indent=2)
    logger.info(f"Saved global importance → {GLOBAL_IMPORTANCE_PATH}")

    # Log top features
    logger.info("Top 5 globally important factors:")
    for feat, val in list(global_importance.items())[:5]:
        label = FEATURE_METADATA.get(feat, {}).get("label", feat)
        logger.info(f"  {label:45s} {val:.4f}")

    # ── Feature metadata JSON ─────────────────────────────────────────────────
    with open(FEATURE_METADATA_PATH, "w") as f:
        json.dump(FEATURE_METADATA, f, indent=2)
    logger.info(f"Saved feature metadata → {FEATURE_METADATA_PATH}")

    logger.info("=== Done ===")


def explain_one(feature_row: dict) -> dict:
    """
    Compute per-feature SHAP values for a single (user, song) feature row.
    Positive values = pushed the score UP; negative = pushed it DOWN.

    This function is called at API request time (cheap — O(features)).
    The explainer must already be loaded; call load_explainer() first.

    Args:
        feature_row: dict with keys matching the FEATURES list.

    Returns:
        dict mapping feature name → SHAP value (float).
    """
    explainer = _get_loaded_explainer()
    features = _get_loaded_features()

    x = pd.DataFrame([feature_row])[features]
    sv = explainer.shap_values(x)[0]
    return {feat: round(float(val), 6) for feat, val in zip(features, sv)}


# ── Lazy-loaded explainer (for API module) ────────────────────────────────────
_explainer_cache = None
_features_cache = None


def _get_loaded_explainer():
    global _explainer_cache
    if _explainer_cache is None:
        if not EXPLAINER_PATH.exists():
            raise RuntimeError(
                f"SHAP explainer not found at {EXPLAINER_PATH}. "
                "Run shap_engine.py first."
            )
        _explainer_cache = joblib.load(EXPLAINER_PATH)
    return _explainer_cache


def _get_loaded_features():
    global _features_cache
    if _features_cache is None:
        if not FEATURES_PATH.exists():
            raise RuntimeError(
                f"Feature list not found at {FEATURES_PATH}. "
                "Run train_surrogate.py first."
            )
        _features_cache = joblib.load(FEATURES_PATH)
    return _features_cache


if __name__ == "__main__":
    build_explainer()
