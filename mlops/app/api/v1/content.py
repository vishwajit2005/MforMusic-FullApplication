"""
Content Model & Feature Extraction API — Part A & B

1. POST /api/v1/content/queue-feature-extraction:
   Receives song_id + audio URL from Spring Boot AsyncUploadService,
   queues background task to extract 63 librosa features, and saves to song_audio_features.
2. POST /api/v1/content/model/retrain:
   Manually triggers background retraining of the NearestNeighbors content similarity model.
3. GET /api/v1/content/model/status:
   Reports model readiness, version, total tracks, and pending un-incorporated audio features.
"""

import logging
import threading
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.models.song_audio_feature import SongAudioFeature, FEATURE_COLUMNS_63
from app.services.audio_feature_extractor import extract_features_from_url
from app.services.content_recommendation_service import content_service

logger = logging.getLogger(__name__)
router = APIRouter()


class FeatureExtractionRequest(BaseModel):
    song_id: str = Field(..., description="JioSaavn externalTrackId")
    audio_url: str = Field(..., description="Public Supabase/S3 audio URL")
    title: Optional[str] = Field(default=None, description="Song title")
    artist_name: Optional[str] = Field(default=None, description="Artist name")
    album: Optional[str] = Field(default=None, description="Album name")
    language: Optional[str] = Field(default="unknown", description="Song language (e.g. hindi, punjabi)")
    decade: Optional[str] = Field(default="2020s", description="Decade (e.g. 2020s, 2010s)")


class ContentModelStatusResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    ready: bool
    retraining: bool
    model_version: str
    total_tracks: int
    unincorporated_tracks: int


def _process_audio_feature_extraction(payload: FeatureExtractionRequest):
    """Background worker to download audio, extract 63 features, and save to DB."""
    logger.info(f"[BG-FeatureExtraction] Starting extraction for song_id={payload.song_id}")
    db = SessionLocal()
    try:
        # Check if already extracted
        existing = db.query(SongAudioFeature).filter(SongAudioFeature.song_id == payload.song_id).first()
        if existing and existing.incorporated_in_model:
            logger.info(f"Song {payload.song_id} features already extracted and incorporated — skipping.")
            return

        features = extract_features_from_url(payload.audio_url)
        if not features:
            logger.warning(f"Could not extract features for {payload.song_id} from {payload.audio_url}")
            return

        if existing:
            # Update
            existing.title = payload.title or existing.title
            existing.artist_name = payload.artist_name or existing.artist_name
            existing.album = payload.album or existing.album
            existing.language = (payload.language or existing.language or "unknown").lower()
            existing.decade = payload.decade or existing.decade or "2020s"
            for col in FEATURE_COLUMNS_63:
                setattr(existing, col, features.get(col, 0.0))
        else:
            # Insert
            row_data = {
                "song_id": payload.song_id,
                "title": payload.title,
                "artist_name": payload.artist_name,
                "album": payload.album,
                "language": (payload.language or "unknown").lower(),
                "decade": payload.decade or "2020s",
                "incorporated_in_model": False,
            }
            for col in FEATURE_COLUMNS_63:
                row_data[col] = features.get(col, 0.0)

            new_row = SongAudioFeature(**row_data)
            db.add(new_row)

        db.commit()
        logger.info(f"[BG-FeatureExtraction] Successfully saved 63 audio features for {payload.song_id} ({payload.title!r})")

    except Exception as e:
        logger.error(f"Error in background feature extraction for {payload.song_id}: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


@router.post(
    "/queue-feature-extraction",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue audio feature extraction for a newly-uploaded track",
)
def queue_feature_extraction(
    payload: FeatureExtractionRequest,
    background_tasks: BackgroundTasks,
):
    """
    Called by Spring Boot AsyncUploadService after audio upload succeeds.
    Runs non-blocking feature extraction in the background.
    """
    background_tasks.add_task(_process_audio_feature_extraction, payload)
    return {
        "status": "queued",
        "song_id": payload.song_id,
        "message": "Audio feature extraction scheduled in background.",
    }


@router.post(
    "/model/retrain",
    summary="Manually trigger content-based similarity model retraining",
    description="Refits the NearestNeighbors model and hot-swaps under lock. Returns immediately.",
)
def trigger_retrain(
    force: bool = Query(default=False, description="Force retrain even if new songs count < MIN_NEW_SONGS threshold"),
):
    if content_service.is_retraining:
        return {
            "status": "already_retraining",
            "model_version": content_service.model_version,
        }

    content_service.trigger_retrain(force=force)
    return {
        "status": "retrain_triggered",
        "force": force,
        "model_version": content_service.model_version,
    }


@router.get(
    "/model/status",
    response_model=ContentModelStatusResponse,
    summary="Get content recommendation model status",
)
def model_status(db: Session = Depends(get_db)):
    unincorporated = (
        db.query(SongAudioFeature)
        .filter(SongAudioFeature.incorporated_in_model == False)  # noqa: E712
        .count()
    )

    stats = content_service.stats
    return ContentModelStatusResponse(
        ready=stats["ready"],
        retraining=stats["retraining"],
        model_version=stats["model_version"],
        total_tracks=stats["total_tracks"],
        unincorporated_tracks=unincorporated,
    )
