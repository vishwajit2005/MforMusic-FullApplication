"""
train_surrogate.py — Phase 2 of the MforMusic Explainability Pipeline
======================================================================
Trains an XGBoost surrogate model on the feature matrix produced by
build_dataset.py and saves the model + feature list as joblib artifacts.

The surrogate approximates the recommendation engine's ranking signal
so that SHAP can explain it. It doesn't need to be perfect — just
directionally faithful enough for explanations to be interpretable.

Usage:
    cd mlops/
    python -m app.explainability.train_surrogate

Artifacts produced (in app/explainability/artifacts/):
    surrogate_model.joblib  — trained XGBRegressor
    feature_list.joblib     — ordered list of feature column names (after one-hot)
"""

import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error

try:
    import xgboost as xgb
except ImportError:
    print("ERROR: xgboost not installed. Run: pip install xgboost")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATASET_PATH = BASE_DIR / "dataset" / "explainability_training_data.parquet"
ARTIFACTS_DIR = BASE_DIR / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PATH = ARTIFACTS_DIR / "surrogate_model.joblib"
FEATURES_PATH = ARTIFACTS_DIR / "feature_list.joblib"

# ── Feature list (SINGLE SOURCE OF TRUTH — keep in sync with other modules) ──
NUMERIC_FEATURES = [
    "likes_count",
    "user_play_count",
    "skip_count",
    "completion_rate",
    "genre_language_match",
    "decade_match",
    "content_similarity_score",
    "popularity_score",
    "recency_days",
]
CATEGORICAL_FEATURES = ["tier_used"]
TARGET_COL = "interaction_score"

# After one-hot encoding tier_used, these are the columns we train on.
# "unknown" is now a valid category — it represents ALL historical rows,
# since the recommendation-serving tier was never logged for past interactions.
# The surrogate will learn that "unknown" rows carry no tier signal, which
# is the honest representation rather than defaulting them into a known tier.
TIER_DUMMIES = [
    "tier_used_collaborative_filtering",
    "tier_used_content_based",
    "tier_used_popular",
    "tier_used_unknown",   # ← ALL historical rows; the dominant category for now
]
FEATURES = NUMERIC_FEATURES + TIER_DUMMIES


def main():
    logger.info("=== MforMusic Surrogate Model Trainer ===")

    # ── Load dataset ──────────────────────────────────────────────────────────
    if not DATASET_PATH.exists():
        logger.error(
            f"Dataset not found at {DATASET_PATH}. "
            "Run build_dataset.py first."
        )
        sys.exit(1)

    df = pd.read_parquet(DATASET_PATH)
    logger.info(f"Loaded dataset: {len(df):,} rows × {len(df.columns)} columns")

    if len(df) < 10:
        logger.warning(
            f"Dataset has only {len(df)} rows — surrogate will be under-trained. "
            "Collect more interaction data before training a meaningful model."
        )

    # ── One-hot encode tier_used ──────────────────────────────────────────────
    df = pd.get_dummies(df, columns=["tier_used"], prefix="tier_used")

    # Ensure ALL four tier dummy columns exist even if some tiers have no data.
    # In particular, "unknown" is the only tier present in fully-historical datasets;
    # the three known tiers will appear once recommendation-serving event logging
    # is added (see README.md — Future Improvement).
    for col in TIER_DUMMIES:
        if col not in df.columns:
            df[col] = 0
            logger.warning(f"Added missing tier column: {col}")

    # ── Ensure all numeric feature columns exist ──────────────────────────────
    for col in NUMERIC_FEATURES:
        if col not in df.columns:
            logger.warning(f"Feature column missing: {col} — filling with 0.")
            df[col] = 0

    X = df[FEATURES].copy()
    y = df[TARGET_COL].copy()

    logger.info(f"Training on {len(FEATURES)} features: {FEATURES}")
    logger.info(f"Target distribution: mean={y.mean():.3f}, std={y.std():.3f}, "
                f"min={y.min():.3f}, max={y.max():.3f}")

    # ── Train / test split ────────────────────────────────────────────────────
    if len(df) >= 20:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
    else:
        # Not enough data for a meaningful split — train on all, report training metrics
        logger.warning("Too few rows for train/test split — reporting training-set metrics.")
        X_train, X_test, y_train, y_test = X, X, y, y

    # ── Train XGBoost surrogate ───────────────────────────────────────────────
    logger.info("Training XGBRegressor surrogate model...")
    model = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbosity=0,
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    # ── Evaluate ──────────────────────────────────────────────────────────────
    y_pred = model.predict(X_test)
    r2 = r2_score(y_test, y_pred)
    mae = mean_absolute_error(y_test, y_pred)
    logger.info(f"Model evaluation — R²: {r2:.4f} | MAE: {mae:.4f}")

    if r2 < 0.3:
        logger.warning(
            f"R² = {r2:.3f} is below the 0.3 threshold suggested in the spec. "
            "Consider adding more interaction data or revisiting the feature list."
        )
    else:
        logger.info("R² passes the 0.3 quality gate ✓")

    # ── Feature importance sanity check ──────────────────────────────────────
    importances = dict(zip(FEATURES, model.feature_importances_))
    top_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)
    logger.info("Top feature importances (XGBoost built-in):")
    for feat, imp in top_features[:5]:
        logger.info(f"  {feat:45s} {imp:.4f}")

    # ── Save artifacts ────────────────────────────────────────────────────────
    joblib.dump(model, MODEL_PATH)
    joblib.dump(FEATURES, FEATURES_PATH)
    logger.info(f"Saved surrogate model → {MODEL_PATH}")
    logger.info(f"Saved feature list    → {FEATURES_PATH}")

    logger.info("=== Done ===")
    return r2, mae


if __name__ == "__main__":
    main()
