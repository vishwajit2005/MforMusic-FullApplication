import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.interaction import InteractionIngest, InteractionIngestResponse
from app.services.recommendation_service import ingest_interaction

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/ingest",
    response_model=InteractionIngestResponse,
    status_code=202,
    summary="Ingest a telemetry interaction event",
    description=(
        "Receives events forwarded by the Spring Boot TelemetryService. "
        "Persists to PostgreSQL and conditionally triggers ALS model retraining."
    ),
)
def ingest(
    payload: InteractionIngest,
    db: Session = Depends(get_db),
):
    try:
        interaction, retrain_triggered = ingest_interaction(db, payload)
        return InteractionIngestResponse(
            status="accepted",
            id=interaction.id,
            retrain_triggered=retrain_triggered,
        )
    except Exception as e:
        logger.error(f"Ingestion error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to store interaction")
