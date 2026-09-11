"""
api.py — Phase 4 of the MforMusic Explainability Pipeline
==========================================================
FastAPI router that exposes three explainability endpoints.

All heavy artifacts (surrogate model, SHAP explainer, global importance,
feature metadata) are loaded ONCE at module import time — not per-request.
The only per-request work is the cheap explain_one() call (O(features)).

Endpoints:
    GET /api/v1/explainability/global-importance
    GET /api/v1/explainability/factors
    GET /api/v1/explainability/recommendation/{user_id}/{song_id}

Registration:
    This router is registered in mlops/app/main.py.
    It is purely additive — no existing routes are modified.
"""

import json
import logging
import math
from pathlib import Path
from typing import Optional

import joblib
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.interaction import Interaction
from app.models.song_audio_feature import SongAudioFeature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/explainability", tags=["Explainability"])

# ── Artifact paths ────────────────────────────────────────────────────────────
_ARTIFACTS_DIR = Path(__file__).parent / "artifacts"

# ── Load artifacts once at import time ───────────────────────────────────────
# The API will still start even if artifacts are missing — endpoints will
# return 503 with a clear error message until the pipeline has been run.

def _try_load(path: Path, label: str):
    try:
        if path.suffix == ".json":
            with open(path) as f:
                return json.load(f)
        return joblib.load(path)
    except FileNotFoundError:
        logger.warning(
            f"[Explainability] {label} not found at {path}. "
            "Run the explainability pipeline first "
            "(build_dataset.py → train_surrogate.py → shap_engine.py)."
        )
        return None
    except Exception as e:
        logger.error(f"[Explainability] Failed to load {label}: {e}")
        return None


_model = _try_load(_ARTIFACTS_DIR / "surrogate_model.joblib", "surrogate model")
_explainer = _try_load(_ARTIFACTS_DIR / "shap_explainer.joblib", "SHAP explainer")
_features = _try_load(_ARTIFACTS_DIR / "feature_list.joblib", "feature list")
_global_importance: Optional[dict] = _try_load(_ARTIFACTS_DIR / "global_importance.json", "global importance")
_feature_meta: Optional[dict] = _try_load(_ARTIFACTS_DIR / "feature_metadata.json", "feature metadata")


def _load_artifacts():
    global _model, _explainer, _features, _global_importance, _feature_meta
    if _model is None:
        _model = _try_load(_ARTIFACTS_DIR / "surrogate_model.joblib", "surrogate model")
    if _explainer is None:
        _explainer = _try_load(_ARTIFACTS_DIR / "shap_explainer.joblib", "SHAP explainer")
    if _features is None:
        _features = _try_load(_ARTIFACTS_DIR / "feature_list.joblib", "feature list")
    if _global_importance is None:
        _global_importance = _try_load(_ARTIFACTS_DIR / "global_importance.json", "global importance")
    if _feature_meta is None:
        _feature_meta = _try_load(_ARTIFACTS_DIR / "feature_metadata.json", "feature metadata")


def _artifacts_ready() -> bool:
    if not all(x is not None for x in [_model, _explainer, _features, _global_importance, _feature_meta]):
        _load_artifacts()
    return all(x is not None for x in [_model, _explainer, _features, _global_importance, _feature_meta])


def _require_artifacts():
    if not _artifacts_ready():
        raise HTTPException(
            status_code=503,
            detail=(
                "Explainability artifacts not yet built. "
                "Run the pipeline: build_dataset.py → train_surrogate.py → shap_engine.py. "
                "Then restart the service."
            ),
        )


# ── Feature row builder ───────────────────────────────────────────────────────

def _safe_log_norm_value(value: float, max_play_count: float = 1_000_000) -> float:
    """Log-normalize a single play count value."""
    log_val = math.log1p(max(value, 0))
    log_max = math.log1p(max_play_count)
    return log_val / log_max if log_max > 0 else 0.0


def build_feature_row(user_id: str, song_id: str, db: Session) -> Optional[dict]:
    """
    Constructs the 12-element feature vector for a (user, song) pair
    using live data from PostgreSQL (interactions, song_audio_features).

    Returns None if the user has no interaction data at all.
    This mirrors the feature engineering in build_dataset.py.
    """
    import pandas as pd
    import time

    # ── Fetch user interactions from PostgreSQL ───────────────────────────────
    user_interactions = (
        db.query(Interaction)
        .filter(Interaction.user_id == user_id)
        .all()
    )
    if not user_interactions:
        return None

    # ── Per (user, song) aggregates ───────────────────────────────────────────
    song_interactions = [i for i in user_interactions if i.song_id == song_id]

    user_play_count = sum(
        1 for i in song_interactions if (i.interaction_type or "").lower() == "play"
    )
    skip_count = sum(
        1 for i in song_interactions if (i.interaction_type or "").lower() == "skip"
    )
    completion_rates = [
        i.completion_rate for i in song_interactions
        if i.completion_rate is not None
    ]
    completion_rate = sum(completion_rates) / len(completion_rates) if completion_rates else 0.0

    # ── Recency (days since last interaction with this song) ──────────────────
    timestamps = [
        i.device_timestamp for i in song_interactions
        if i.device_timestamp is not None and i.device_timestamp > 0
    ]
    if timestamps:
        last_ts_ms = max(timestamps)
        now_ms = time.time() * 1000
        recency_days = (now_ms - last_ts_ms) / 86_400_000
    else:
        # User never interacted with this specific song — use a large value
        recency_days = 999.0

    # ── Like count for this song (from all users) ─────────────────────────────
    # We approximate with the PostgreSQL interactions table (like events across all users)
    like_count_result = (
        db.query(Interaction)
        .filter(
            Interaction.song_id == song_id,
            Interaction.interaction_type == "like",
        )
        .count()
    )
    likes_count = like_count_result

    # ── Audio features: language and decade ───────────────────────────────────
    audio_feat = (
        db.query(SongAudioFeature)
        .filter(SongAudioFeature.song_id == song_id)
        .first()
    )
    song_language = audio_feat.language if audio_feat else None
    song_decade = audio_feat.decade if audio_feat else None

    # ── User's favorite language and decade ──────────────────────────────────
    all_song_ids = list({i.song_id for i in user_interactions})

    if all_song_ids:
        user_audio_features = (
            db.query(SongAudioFeature)
            .filter(SongAudioFeature.song_id.in_(all_song_ids))
            .all()
        )
        lang_counts: dict = {}
        decade_counts: dict = {}
        for af in user_audio_features:
            if af.language:
                lang_counts[af.language] = lang_counts.get(af.language, 0) + 1
            if af.decade:
                decade_counts[af.decade] = decade_counts.get(af.decade, 0) + 1

        user_fav_language = max(lang_counts, key=lang_counts.get) if lang_counts else None
        user_fav_decade = max(decade_counts, key=decade_counts.get) if decade_counts else None
    else:
        user_fav_language = None
        user_fav_decade = None

    genre_language_match = int(
        song_language is not None
        and user_fav_language is not None
        and song_language.lower() == user_fav_language.lower()
    )
    decade_match = int(
        song_decade is not None
        and user_fav_decade is not None
        and song_decade == user_fav_decade
    )

    # ── content_similarity_score — not logged at rec time → default 0.0 ───────
    content_similarity_score = 0.0

    # ── Popularity score — proxy via like count (normalized) ──────────────────
    # In a full implementation, join to MySQL songs.play_count here.
    # For the API we use a simple log-normalized like count as a proxy.
    popularity_score = _safe_log_norm_value(likes_count, max_play_count=10_000)

    # ── tier_used — infer same heuristic as build_dataset.py ─────────────────
    if user_play_count >= 3:
        tier = "collaborative_filtering"
    elif content_similarity_score > 0:
        tier = "content_based"
    else:
        tier = "popular"

    tier_cf = int(tier == "collaborative_filtering")
    tier_cb = int(tier == "content_based")
    tier_pop = int(tier == "popular")
    tier_unk = int(tier == "unknown")

    return {
        "likes_count": likes_count,
        "user_play_count": user_play_count,
        "skip_count": skip_count,
        "completion_rate": completion_rate,
        "genre_language_match": genre_language_match,
        "decade_match": decade_match,
        "content_similarity_score": content_similarity_score,
        "popularity_score": popularity_score,
        "recency_days": recency_days,
        "tier_used_collaborative_filtering": tier_cf,
        "tier_used_content_based": tier_cb,
        "tier_used_popular": tier_pop,
        "tier_used_unknown": tier_unk,
        # Keep tier_used as string for response context (not used in model input)
        "_tier_used_str": tier,
    }


def _explain_one(feature_row: dict) -> dict:
    """Run SHAP for a single feature row. Artifacts must be loaded."""
    import pandas as pd

    # Remove internal keys not used by the model
    model_row = {k: v for k, v in feature_row.items() if not k.startswith("_")}
    df_row = pd.DataFrame([model_row])
    for f in _features:
        if f not in df_row.columns:
            df_row[f] = 0
    x = df_row[_features]
    sv = _explainer.shap_values(x)[0]
    return {feat: round(float(val), 6) for feat, val in zip(_features, sv)}


def _auto_summary(shap_values: dict, feature_meta: dict) -> str:
    """
    Generate a one-line human-readable explanation.
    E.g. "Driven mostly by Your Play History (+0.42) and Language Match (+0.18);
          pulled down slightly by Days Since You Last Listened (−0.05)."
    """
    sorted_by_abs = sorted(shap_values.items(), key=lambda x: abs(x[1]), reverse=True)
    positives = [(f, v) for f, v in sorted_by_abs if v > 0][:2]
    negatives = [(f, v) for f, v in sorted_by_abs if v < 0][:1]

    def _label(feat: str) -> str:
        return feature_meta.get(feat, {}).get("label", feat)

    parts = []
    if positives:
        driven = " and ".join(f"{_label(f)} ({v:+.2f})" for f, v in positives)
        parts.append(f"Driven mostly by {driven}")
    if negatives:
        pulled = ", ".join(f"{_label(f)} ({v:+.2f})" for f, v in negatives)
        parts.append(f"pulled down slightly by {pulled}")

    return "; ".join(parts) + "." if parts else "No strong factors identified."


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/global-importance",
    summary="Global factor importance ranking",
    description=(
        "Returns the mean absolute SHAP value per feature across the entire training dataset. "
        "Higher values indicate that factor has more influence on recommendation scores overall."
    ),
)
def global_importance():
    _require_artifacts()
    return {"factors": _global_importance}


@router.get(
    "/factors",
    summary="Human-readable factor names and descriptions",
    description=(
        "Returns a metadata dictionary mapping each feature name to its human-readable label "
        "and one-line description, suitable for use as UI labels in the dashboard."
    ),
)
def factor_metadata():
    _require_artifacts()
    return _feature_meta


@router.get(
    "/recommendation/{user_id}/{song_id}",
    summary="Explain why a specific song was recommended to a user",
    description=(
        "Returns per-factor SHAP values for the (user_id, song_id) pair. "
        "Positive values pushed the recommendation score up; negative values pulled it down. "
        "Also returns a predicted_score from the surrogate and an auto-generated text summary."
    ),
)
def explain_recommendation(
    user_id: str,
    song_id: str,
    db: Session = Depends(get_db),
):
    _require_artifacts()

    import pandas as pd

    # Build feature row from live DB
    feature_row = build_feature_row(user_id, song_id, db)
    if feature_row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No interaction data found for user '{user_id}'. "
                "The user must have at least one interaction to generate an explanation."
            ),
        )

    # Predicted score from surrogate
    model_input_row = {k: v for k, v in feature_row.items() if not k.startswith("_")}
    df_pred = pd.DataFrame([model_input_row])
    for f in _features:
        if f not in df_pred.columns:
            df_pred[f] = 0
    x = df_pred[_features]
    predicted_score = float(_model.predict(x)[0])

    # SHAP values
    shap_values = _explain_one(feature_row)

    # Auto-generated text summary
    summary = _auto_summary(shap_values, _feature_meta)

    return {
        "user_id": user_id,
        "song_id": song_id,
        "tier_used": feature_row.get("_tier_used_str", "unknown"),
        "predicted_score": round(predicted_score, 4),
        "shap_values": shap_values,
        "summary": summary,
    }


@router.get(
    "/status",
    summary="Explainability artifacts status",
    description="Reports whether all explainability artifacts have been built and loaded.",
)
def artifacts_status():
    return {
        "artifacts_ready": _artifacts_ready(),
        "surrogate_model_loaded": _model is not None,
        "shap_explainer_loaded": _explainer is not None,
        "feature_list_loaded": _features is not None,
        "global_importance_loaded": _global_importance is not None,
        "feature_metadata_loaded": _feature_meta is not None,
        "artifacts_dir": str(_ARTIFACTS_DIR),
    }


@router.get(
    "/users",
    summary="Get recent users with interaction counts",
)
def list_recent_users(db: Session = Depends(get_db)):
    from sqlalchemy import func
    results = (
        db.query(
            Interaction.user_id,
            func.count(Interaction.id).label("interaction_count"),
            func.max(Interaction.created_at).label("last_active")
        )
        .group_by(Interaction.user_id)
        .order_by(func.max(Interaction.created_at).desc())
        .limit(30)
        .all()
    )
    return [
        {
            "user_id": r[0],
            "interaction_count": r[1],
            "last_active": r[2].isoformat() if r[2] else None
        }
        for r in results
    ]


@router.get(
    "/user-interactions/{user_id}",
    summary="Get interaction logs for a user",
)
def get_user_interactions(user_id: str, limit: int = 50, db: Session = Depends(get_db)):
    rows = (
        db.query(Interaction)
        .filter(Interaction.user_id == user_id)
        .order_by(Interaction.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "song_id": r.song_id,
            "interaction_type": r.interaction_type,
            "play_duration_sec": r.play_duration_sec,
            "completion_rate": r.completion_rate,
            "session_id": r.session_id,
            "device_timestamp": r.device_timestamp,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


class InteractionCreatePayload(BaseModel):
    user_id: str
    song_id: str
    interaction_type: str
    play_duration_sec: int = 120
    completion_rate: float = 0.8
    session_id: str = "web_session"


@router.post(
    "/interactions",
    summary="Add an interaction for a user",
)
def add_interaction(payload: InteractionCreatePayload, db: Session = Depends(get_db)):
    import time
    from app.services.recommendation_service import ingest_interaction
    from app.schemas.interaction import InteractionIngest
    ingest_payload = InteractionIngest(
        user_id=payload.user_id,
        song_id=payload.song_id,
        interaction_type=payload.interaction_type,
        play_duration_sec=payload.play_duration_sec,
        completion_rate=payload.completion_rate,
        session_id=payload.session_id,
        device_timestamp=int(time.time() * 1000),
    )
    interaction, retrain_triggered = ingest_interaction(db, ingest_payload)
    return {
        "status": "success",
        "interaction_id": interaction.id,
        "user_id": interaction.user_id,
        "song_id": interaction.song_id,
        "interaction_type": interaction.interaction_type,
        "retrain_triggered": retrain_triggered
    }
