import logging
from typing import Annotated
from pydantic import StringConstraints

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.recommendation import RecommendationResponse, ModelStatusResponse, SimilarSongsResponse
from app.services.cf_engine import cf_engine
from app.core.config import get_settings
from app.services.recommendation_metrics import recommendation_metrics
from app.services.recommendation_service import get_recommendations, get_similar_recommendations

logger = logging.getLogger(__name__)
router = APIRouter()


SongId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


# Static route must precede /{user_id}, otherwise "similar" is treated as a user.
@router.get(
    "/similar",
    response_model=SimilarSongsResponse,
    summary="Songs matching the Now Playing listening window",
    description=(
        "Current song plus up to four prior plays, newest first. Current weight "
        "70; context weights 12,8,6,4 multiplied by latest-positive interaction quality. "
        "Recent strong rejects softly re-rank candidates. Unknown tracks are skipped. All seed and "
        "user-interacted IDs are excluded. No CF or popular fallback. This mode "
        "does not enter the For You serving-distribution counter."
    ),
)
def similar_songs(
    user_id: Annotated[str, Query(min_length=1, max_length=64)],
    current_song_id: Annotated[SongId, Query()],
    context_song_ids: Annotated[list[SongId], Query(max_length=4)] = [],
    n: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    try:
        return get_similar_recommendations(user_id, current_song_id, context_song_ids, db, n)
    except Exception:
        logger.exception("Similar Songs request failed")
        raise HTTPException(status_code=500, detail="Failed to compute similar songs")


@router.get(
    "/{user_id}",
    response_model=RecommendationResponse,
    summary="Get personalized recommendations for a user",
    description=(
        "Returns up to `n` song recommendations. "
        "Tries content-based and eligible ALS recommendations in the configured order; "
        "falls back to globally popular songs for cold-start users."
    ),
)
def recommend(
    user_id: str,
    n: int = Query(default=20, ge=1, le=50, description="Number of recommendations to return"),
    db: Session = Depends(get_db),
):
    diagnostics = {}
    priority = get_settings().RECOMMENDATION_PRIORITY
    try:
        result = get_recommendations(user_id=user_id, db=db, n=n, diagnostics=diagnostics)
    except Exception as e:
        logger.error(f"Recommendation error for user {user_id}: {e}", exc_info=True)
        recommendation_metrics.record("error", priority)
        raise HTTPException(status_code=500, detail="Failed to compute recommendations")
    reason = diagnostics.get("content_fallback_reason") if result["source"] in ("popular", "cold_start") else None
    recommendation_metrics.record(result["source"], priority, reason)
    logger.info("[RecommendationOutcome] source=%s priority=%s fallback_reason=%s",
                result["source"], priority, reason)
    return result


@router.get(
    "/metrics/distribution",
    summary="For You serving distribution over the last 100 requests",
    description=(
        "Process-local rolling counts; resets on restart. Includes successful "
        "recommendation-handler calls and handler errors, not validation/auth "
        "rejections. Dashboard recommendation fetches also count. Percentages "
        "use observed_requests as denominator, including cold_start and error. "
        "fallback_reasons counts popular and cold_start outcomes only."
    ),
)
def recommendation_distribution():
    return recommendation_metrics.snapshot()


@router.get(
    "/model/status",
    response_model=ModelStatusResponse,
    summary="Get CF model training status",
)
def model_status():
    stats = cf_engine.stats
    return ModelStatusResponse(
        trained=stats["trained"],
        model_version=stats["model_version"],
        total_interactions=stats["total_interactions"],
        total_users=stats["total_users"],
        total_songs=stats["total_songs"],
    )


@router.post(
    "/model/retrain",
    summary="Manually trigger model retraining",
    description="Triggers a background ALS retrain. Returns immediately.",
)
def trigger_retrain():
    if cf_engine._is_retraining:
        return {"status": "already_retraining", "model_version": cf_engine.model_version}
    cf_engine.trigger_retrain()
    return {"status": "retrain_triggered", "model_version": cf_engine.model_version}
