"""
Recommendation Service — orchestrates the CF engine, handles cold start,
tracks interaction counts, and triggers retraining.
"""

import logging
import threading

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.interaction import Interaction
from app.models.song_embedding import SongEmbedding
from app.schemas.interaction import InteractionIngest
from app.services.cf_engine import cf_engine
from app.services.embedding_service import embed_song

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Retrain counter (thread-safe) ─────────────────────────────────────────────
_interaction_count = 0
_count_lock = threading.Lock()


def ingest_interaction(db: Session, payload: InteractionIngest) -> tuple[Interaction, bool]:
    """
    Persists the interaction to PostgreSQL and conditionally triggers a retrain.

    Returns:
        (saved_interaction, retrain_triggered)
    """
    global _interaction_count

    interaction = Interaction(
        user_id=payload.user_id,
        song_id=payload.song_id,
        interaction_type=payload.interaction_type,
        play_duration_sec=payload.play_duration_sec,
        completion_rate=payload.completion_rate,
        session_id=payload.session_id,
        device_timestamp=payload.device_timestamp,
    )
    db.add(interaction)
    db.commit()
    db.refresh(interaction)

    # ── Upsert song embedding (Phase 6) ──────────────────────────────────────
    # On first encounter of a song_id, generate and store its embedding so it
    # becomes available for semantic search and content-based recommendations.
    _upsert_song_embedding_async(db, payload)

    logger.info(
        f"[Ingest] user={payload.user_id} song={payload.song_id} "
        f"type={payload.interaction_type} completion={payload.completion_rate:.2f}"
    )

    # Check if we've hit the retrain threshold
    retrain_triggered = False
    with _count_lock:
        _interaction_count += 1
        if _interaction_count >= settings.RETRAIN_EVERY_N_INTERACTIONS:
            _interaction_count = 0
            retrain_triggered = True

    if retrain_triggered:
        logger.info(
            f"Retrain threshold ({settings.RETRAIN_EVERY_N_INTERACTIONS}) reached — "
            "triggering background CF retrain."
        )
        cf_engine.trigger_retrain()

    return interaction, retrain_triggered


def get_recommendations(
    user_id: str,
    db: Session,
    n: int | None = None,
) -> dict:
    """
    Returns personalized recommendations for user_id.

    Strategy:
      1. If model untrained OR user has < MIN_INTERACTIONS_FOR_CF → popular fallback
      2. If model trained but user not in model (joined after last retrain) → popular fallback
      3. Normal path → ALS collaborative filtering
    """
    top_n = n or settings.TOP_N_RECOMMENDATIONS

    # Count this user's interactions
    user_count = (
        db.query(Interaction)
        .filter(Interaction.user_id == user_id)
        .count()
    )

    # ── Cold start ────────────────────────────────────────────────────────────
    if not cf_engine.is_trained or user_count < settings.MIN_INTERACTIONS_FOR_CF:
        logger.info(
            f"[Recs] Cold start for user={user_id} "
            f"(interactions={user_count}, model_trained={cf_engine.is_trained}). "
            "Returning popular songs."
        )
        songs = cf_engine.get_popular_songs(db, top_n)
        return {
            "user_id": user_id,
            "recommendations": songs,
            "model_version": cf_engine.model_version,
            "total": len(songs),
            "source": "popular" if songs else "cold_start",
        }

    # ── CF recommendations ────────────────────────────────────────────────────
    recs = cf_engine.recommend_for_user(user_id, top_n)

    if not recs:
        # User exists in DB but not in current model (joined after last retrain)
        logger.info(
            f"[Recs] User {user_id} not in current model — falling back to popular."
        )
        songs = cf_engine.get_popular_songs(db, top_n)
        return {
            "user_id": user_id,
            "recommendations": songs,
            "model_version": cf_engine.model_version,
            "total": len(songs),
            "source": "popular",
        }

    logger.info(
        f"[Recs] CF recommendations for user={user_id}: "
        f"{len(recs)} tracks (model={cf_engine.model_version})"
    )
    return {
        "user_id": user_id,
        "recommendations": recs,
        "model_version": cf_engine.model_version,
        "total": len(recs),
        "source": "collaborative_filtering",
    }


# ── Phase 6: embedding upsert ─────────────────────────────────────────────────

def _upsert_song_embedding_async(db: Session, payload: InteractionIngest):
    """
    Non-blocking: spawn a daemon thread to generate + store song embedding.
    Only runs on first encounter of each song_id to avoid redundant work.

    NOTE: Since InteractionIngest only carries song_id (JioSaavn externalTrackId),
    the embedding uses song_id as text input until Spring Boot enriches the
    SongEmbedding row with proper title + artist via the /ingest endpoint.
    Spring Boot must forward `song_title` and `song_artist` for quality embeddings.
    """
    def _worker():
        from app.core.database import SessionLocal
        bg_db = SessionLocal()
        try:
            existing = bg_db.query(SongEmbedding).filter(
                SongEmbedding.song_id == payload.song_id
            ).first()

            if existing is not None and existing.embedding is not None:
                return  # Already embedded — skip

            # Use song_title + song_artist if provided in payload, else fall back to song_id
            title = getattr(payload, "song_title", None) or payload.song_id
            artist = getattr(payload, "song_artist", None)

            vec = embed_song(title, artist)
            if vec is None:
                return

            if existing:
                # Update embedding; also update title/artist if now available
                existing.embedding = vec.tolist()
                if getattr(payload, "song_title", None):
                    existing.title = payload.song_title
                if getattr(payload, "song_artist", None):
                    existing.artist_name = payload.song_artist
            else:
                new_entry = SongEmbedding(
                    song_id=payload.song_id,
                    title=title,           # placeholder until enriched by Spring Boot
                    artist_name=artist,
                    embedding=vec.tolist(),
                )
                bg_db.add(new_entry)
            bg_db.commit()
            logger.debug(f"Song embedding stored for song_id={payload.song_id} title={title!r}")
        except Exception as e:
            logger.warning(f"Embedding upsert failed for {payload.song_id}: {e}")
            bg_db.rollback()
        finally:
            bg_db.close()

    t = threading.Thread(target=_worker, name=f"embed-{payload.song_id[:8]}", daemon=True)
    t.start()
