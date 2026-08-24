import logging

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.recommendation import RecommendationResponse, ModelStatusResponse
from app.services.cf_engine import cf_engine
from app.services.recommendation_service import get_recommendations

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/{user_id}",
    response_model=RecommendationResponse,
    summary="Get personalized recommendations for a user",
    description=(
        "Returns up to `n` song recommendations. "
        "Uses ALS collaborative filtering if the user has enough history; "
        "falls back to globally popular songs for cold-start users."
    ),
)
def recommend(
    user_id: str,
    n: int = Query(default=20, ge=1, le=50, description="Number of recommendations to return"),
    db: Session = Depends(get_db),
):
    try:
        result = get_recommendations(user_id=user_id, db=db, n=n)
        return result
    except Exception as e:
        logger.error(f"Recommendation error for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to compute recommendations")


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
