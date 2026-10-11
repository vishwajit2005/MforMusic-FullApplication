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
from app.services import embedding_recommender
from app.services.version_dedup import build_metadata, collapse_versions

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


# ── Post-processing helpers (never change model scores) ──────────────────────

# Candidates fetched per requested slot, so dropping duplicate versions still fills n.
_OVERFETCH = 3
_MAX_BLOCKED_FOR_METADATA = 200


def _fetch_size(n: int) -> int:
    return max(n, min(n * _OVERFETCH, n + 40))


def _finalize(recs: list[dict], n: int, db: Session, blocked_ids, extra_metadata: dict | None = None) -> list[dict]:
    """Collapse multiple versions of the same song, drop versions of blocked songs, trim to n."""
    if not recs:
        return []
    blocked = list(dict.fromkeys(str(b) for b in blocked_ids))[:_MAX_BLOCKED_FOR_METADATA]
    metadata = build_metadata(
        [r["song_id"] for r in recs] + blocked,
        content_service.get_track_metadata,
        lambda ids: embedding_recommender.stored_metadata(db, ids),
    )
    for sid, pair in (extra_metadata or {}).items():
        metadata.setdefault(str(sid), pair)
    return collapse_versions(recs, metadata, n, blocked)


def _blend(primary: list[dict], secondary: list[dict], secondary_share: float, limit: int) -> list[dict]:
    """Interleave two ranked lists so roughly `secondary_share` of slots come from `secondary`."""
    share = min(1.0, max(0.0, secondary_share))
    out, seen = [], set()
    p = s = taken_secondary = 0
    while len(out) < limit and (p < len(primary) or s < len(secondary)):
        want_secondary = taken_secondary < round((len(out) + 1) * share)
        if (want_secondary and s < len(secondary)) or p >= len(primary):
            rec, s = secondary[s], s + 1
            from_secondary = True
        else:
            rec, p = primary[p], p + 1
            from_secondary = False
        if rec["song_id"] in seen:
            continue
        seen.add(rec["song_id"])
        taken_secondary += from_secondary
        out.append(rec)
    return out


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
    fetch_n = _fetch_size(top_n)
    # Most-recent-first unique IDs, used to block other versions of songs already heard.
    recent_interacted_ids = list(dict.fromkeys(i.song_id for i in user_interactions))
    positive_types = {"like", "play", "download", "playlist_add"}
    recent_positive_track_ids = list(islice(
        (
            i.song_id for i in user_interactions
            if (i.interaction_type or "").lower() in positive_types
        ),
        10,
    ))

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
            recs = _finalize(cf_engine.recommend_for_user(user_id, fetch_n), top_n, db, interacted_song_ids)
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
            if recent_positive_track_ids:
                content_recs = content_service.get_taste_recommendations(
                    recent_positive_track_ids=recent_positive_track_ids,
                    n=fetch_n,
                    exclude_ids=interacted_song_ids,
                )
                content_recs = _blend_unknown_seeds(
                    db, content_recs, recent_positive_track_ids, fetch_n, interacted_song_ids,
                )
                content_recs = _finalize(content_recs, top_n, db, recent_interacted_ids)
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

    # ── Tier 2.5: title+artist embeddings (songs outside the audio catalog) ───
    if recent_positive_track_ids:
        weights = [10 - rank for rank in range(len(recent_positive_track_ids))]
        emb_recs = _finalize(
            embedding_recommender.taste_recommendations(
                db, recent_positive_track_ids, weights, fetch_n, interacted_song_ids,
            ),
            top_n, db, recent_interacted_ids,
        )
        if emb_recs:
            logger.info(f"[Recs] Embedding-based recommendations for user={user_id}: {len(emb_recs)} tracks")
            return {
                "user_id": user_id,
                "recommendations": emb_recs,
                "model_version": "title_artist_minilm",
                "total": len(emb_recs),
                "source": "embedding_based",
            }

    # ── Tier 3: Popular Songs Fallback ────────────────────────────────────────
    logger.info(
        f"[Recs] Cold start fallback to popular songs for user={user_id} "
        f"(interactions={user_count}, cf_trained={cf_engine.is_trained}, content_ready={content_service.is_ready})."
    )
    songs = _finalize(cf_engine.get_popular_songs(db, fetch_n), top_n, db, recent_interacted_ids)
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
    current_song_title: str | None = None,
    current_song_artist: str | None = None,
) -> dict:
    """Now Playing only: exclude complete history, never invoke CF/popular.

    If the current song is outside the audio catalog, its title+artist embedding
    leads the list (so results follow what is actually playing) and the usual
    context-based audio results fill the remaining slots.
    """
    # One read serves exclusions, latest-positive quality and recent rejections.
    history = (
        db.query(Interaction).filter(Interaction.user_id == user_id)
        .order_by(Interaction.created_at.desc(), Interaction.id.desc()).all()
    )
    interacted_song_ids = {event.song_id for event in history}
    fetch_n = _fetch_size(n)
    recommendations = content_service.get_now_playing_recommendations(
        current_track_id=current_song_id,
        context_track_ids=context_song_ids,
        n=fetch_n,
        exclude_ids=interacted_song_ids,
        interaction_history=history,
    )
    source = "content_based"
    if not content_service.has_track(current_song_id):
        embedding_recs = embedding_recommender.similar_to_song(
            db, current_song_id, fetch_n * 2,
            exclude_ids=set(interacted_song_ids) | set(context_song_ids),
            title=current_song_title, artist=current_song_artist,
        )
        if embedding_recs:
            recommendations = _blend(recommendations, embedding_recs, 1.0, fetch_n * 3)
            source = "embedding_based"
    blocked = [current_song_id] + list(context_song_ids) + list(dict.fromkeys(e.song_id for e in history))
    # Title/artist sent by the backend lets us block other versions of the song playing now.
    current_meta = {current_song_id: (current_song_title, current_song_artist)} if current_song_title else None
    recommendations = _finalize(recommendations, n, db, blocked, current_meta)
    return {
        "user_id": user_id,
        "current_song_id": current_song_id,
        "recommendations": recommendations,
        "model_version": content_service.model_version if source == "content_based" else "title_artist_minilm",
        "total": len(recommendations),
        "source": source,
    }


def _blend_unknown_seeds(db: Session, content_recs: list[dict], positive_ids: list[str],
                         fetch_n: int, interacted_song_ids) -> list[dict]:
    """
    Songs outside the audio catalog contribute nothing to the KNN taste vector.
    Give them a share of the list (by their recency weight) via title+artist embeddings.
    Returns content_recs unchanged when every seed is known or embeddings are unavailable.
    """
    try:
        weights = [10 - rank for rank in range(len(positive_ids))]
        unknown = [(sid, w) for sid, w in zip(positive_ids, weights) if not content_service.has_track(sid)]
        if not unknown or not content_recs:
            return content_recs
        share = sum(w for _, w in unknown) / sum(weights)
        exclude = set(interacted_song_ids) | {r["song_id"] for r in content_recs}
        emb = embedding_recommender.taste_recommendations(
            db, [sid for sid, _ in unknown], [w for _, w in unknown], fetch_n, exclude,
        )
        return _blend(content_recs, emb, share, fetch_n) if emb else content_recs
    except Exception:
        logger.warning("Unknown-seed embedding blend failed; using audio model only", exc_info=True)
        return content_recs


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
