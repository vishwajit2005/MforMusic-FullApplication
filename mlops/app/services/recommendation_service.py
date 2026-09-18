"""
Recommendation Service — orchestrates the CF engine, handles cold start,
tracks interaction counts, and triggers retraining.
"""

import logging
import threading
from itertools import islice

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.interaction import Interaction
from app.models.song_embedding import SongEmbedding
from app.schemas.interaction import InteractionIngest
from app.services.cf_engine import cf_engine
from app.services.content_recommendation_service import content_service
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
    diagnostics: dict | None = None,
) -> dict:
    """
    Returns personalized recommendations for user_id via a 3-tier fallback strategy:
      Content-based taste profile and eligible CF are attempted in the order
      selected by RECOMMENDATION_PRIORITY (content_first by default).
      Popular songs remain the final fallback. Training is independent of order.
    """
    top_n = n or settings.TOP_N_RECOMMENDATIONS

    # Fetch user's interaction history (most recent first)
    user_interactions = (
        db.query(Interaction)
        .filter(Interaction.user_id == user_id)
        .order_by(Interaction.created_at.desc(), Interaction.id.desc())
        .all()
    )
    user_count = len(user_interactions)
    interacted_song_ids = {i.song_id for i in user_interactions}

    # This controls serving only. Ingestion and scheduled retraining still run
    # independently, even when content recommendations satisfy every request.
    tier_order = (
        ("content", "cf") if settings.RECOMMENDATION_PRIORITY == "content_first"
        else ("cf", "content")
    )
    for tier in tier_order:
        if tier == "content" and diagnostics is not None:
            diagnostics["content_fallback_reason"] = (
                "content_model_unavailable" if not content_service.is_ready
                else "no_history" if not user_interactions
                else "no_positive_history"
            )
        if tier == "cf" and cf_engine.is_trained and user_count >= settings.MIN_INTERACTIONS_FOR_CF:
            recs = cf_engine.recommend_for_user(user_id, top_n)
            if recs:
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
            logger.info(
                f"[Recs] CF returned no recommendations for user={user_id} — trying the next tier."
            )

        if tier == "content" and content_service.is_ready and user_interactions:
            # STRICT POSITIVE SIGNALS ONLY: like, play, download, playlist_add
            # Negative signals (skip, unlike) are strictly forbidden from acting as seeds.
            positive_types = {"like", "play", "download", "playlist_add"}
            recent_positive_track_ids = list(islice(
                (
                    i.song_id for i in user_interactions
                    if (i.interaction_type or "").lower() in positive_types
                ),
                10,
            ))

            if recent_positive_track_ids:
                content_recs = content_service.get_taste_recommendations(
                    recent_positive_track_ids=recent_positive_track_ids,
                    n=top_n,
                    exclude_ids=interacted_song_ids,
                )
                if not content_recs and diagnostics is not None:
                    # An empty query can also mean exhausted candidates or a
                    # query failure; only mark coverage when no seed matches.
                    diagnostics["content_fallback_reason"] = (
                        "no_recent_catalog_match"
                        if not any(content_service.has_track(tid) for tid in recent_positive_track_ids)
                        else "no_content_results"
                    )
                if content_recs:
                    logger.info(
                        f"[Recs] Content-based recommendations for user={user_id} "
                        f"(positive_window={len(recent_positive_track_ids)}): {len(content_recs)} tracks "
                        f"(model={content_service.model_version})"
                    )
                    return {
                        "user_id": user_id,
                        "recommendations": content_recs,
                        "model_version": content_service.model_version,
                        "total": len(content_recs),
                        "source": "content_based",
                    }

    # ── Tier 3: Popular Songs Fallback ────────────────────────────────────────
    logger.info(
        f"[Recs] Cold start fallback to popular songs for user={user_id} "
        f"(interactions={user_count}, cf_trained={cf_engine.is_trained}, content_ready={content_service.is_ready})."
    )
    songs = cf_engine.get_popular_songs(db, top_n)
    return {
        "user_id": user_id,
        "recommendations": songs,
        "model_version": cf_engine.model_version,
        "total": len(songs),
        "source": "popular" if songs else "cold_start",
    }


def get_similar_recommendations(
    user_id: str,
    current_song_id: str,
    context_song_ids: list[str],
    db: Session,
    n: int = 20,
) -> dict:
    """Now Playing only: exclude complete history, never invoke CF/popular."""
    # One read serves exclusions, latest-positive quality and recent rejections.
    history = (
        db.query(Interaction).filter(Interaction.user_id == user_id)
        .order_by(Interaction.created_at.desc(), Interaction.id.desc()).all()
    )
    interacted_song_ids = {event.song_id for event in history}
    recommendations = content_service.get_now_playing_recommendations(
        current_track_id=current_song_id,
        context_track_ids=context_song_ids,
        n=n,
        exclude_ids=interacted_song_ids,
        interaction_history=history,
    )
    return {
        "user_id": user_id,
        "current_song_id": current_song_id,
        "recommendations": recommendations,
        "model_version": content_service.model_version,
        "total": len(recommendations),
        "source": "content_based",
    }


# ── Phase 6: embedding upsert ─────────────────────────────────────────────────

def _upsert_song_embedding_async(db: Session, payload: InteractionIngest):
    """
    Non-blocking: spawn a daemon thread to generate + store song embedding.
    Resolves human-readable title & artist from payload or content_service metadata.
    Avoids storing raw opaque IDs as titles.
    """
    def _worker():
        from app.core.database import SessionLocal
        bg_db = SessionLocal()
        try:
            # 1. Resolve human-readable title & artist
            title = getattr(payload, "song_title", None)
            artist = getattr(payload, "song_artist", None)

            # If title is missing or equals song_id, lookup from candidate dataset
            if not title or title == payload.song_id:
                meta = content_service.get_track_metadata(payload.song_id)
                if meta:
                    title = meta.get("title")
                    if not artist:
                        artist = meta.get("artist")

            existing = bg_db.query(SongEmbedding).filter(
                SongEmbedding.song_id == payload.song_id
            ).first()

            # If existing already has valid title and embedding, skip
            if (
                existing is not None
                and existing.embedding is not None
                and existing.title
                and existing.title != payload.song_id
            ):
                return

            # If we still have no title, don't generate garbage embedding on opaque ID
            if not title or title == payload.song_id:
                if existing and existing.title and existing.title != payload.song_id:
                    title = existing.title
                    artist = artist or existing.artist_name
                else:
                    logger.debug(f"Skipping embedding for {payload.song_id}: no human-readable title available.")
                    return

            vec = embed_song(title, artist)
            if vec is None:
                return

            if existing:
                existing.embedding = vec.tolist()
                existing.title = title
                if artist:
                    existing.artist_name = artist
            else:
                new_entry = SongEmbedding(
                    song_id=payload.song_id,
                    title=title,
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
