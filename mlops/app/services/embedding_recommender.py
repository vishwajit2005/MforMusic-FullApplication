"""
Title + artist embedding recommender — fallback for songs the audio KNN model
does not know.

The content (audio-feature) model only covers the songs in its catalog
(app/data/content_model). When a user plays something outside that catalog, the
KNN model has no vector for it. This module covers that gap using the 384-dim
"{title} by {artist}" sentence embeddings already stored in the pgvector table
`song_embeddings` (filled by ingestion and by seed_catalog_embeddings below).

Everything here is best-effort: every public function returns [] / None on any
failure (pgvector missing, embedding service asleep, ...), so the existing
recommendation tiers keep working exactly as before.
"""

import logging
import os
import threading
import time
from typing import Any, Iterable

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.version_dedup import Metadata

logger = logging.getLogger(__name__)


def _vec_literal(vec: np.ndarray) -> str:
    return "[" + ",".join(f"{float(v):.6f}" for v in vec.tolist()) + "]"


def _parse_vec(raw: Any) -> np.ndarray | None:
    if raw is None:
        return None
    try:
        if isinstance(raw, str):
            raw = [float(x) for x in raw.strip("[]").split(",") if x.strip()]
        vec = np.asarray(raw, dtype=np.float32)
        return vec if vec.ndim == 1 and vec.size and np.isfinite(vec).all() else None
    except Exception:
        return None


def _run(db: Session, sql: str, params: dict) -> list:
    """Run a read query inside a SAVEPOINT so a failure cannot poison the caller's transaction."""
    with db.begin_nested():
        return list(db.execute(text(sql), params).fetchall())


def stored_vectors(db: Session, song_ids: Iterable[str]) -> dict[str, np.ndarray]:
    ids = list(dict.fromkeys(str(s) for s in song_ids))
    if not ids:
        return {}
    try:
        rows = _run(db, """
            SELECT song_id, embedding::text AS embedding FROM song_embeddings
            WHERE song_id = ANY(:ids) AND embedding IS NOT NULL
        """, {"ids": ids})
        out = {}
        for row in rows:
            vec = _parse_vec(row.embedding)
            if vec is not None:
                out[str(row.song_id)] = vec
        return out
    except Exception:
        logger.debug("stored_vectors lookup failed", exc_info=True)
        return {}


def stored_metadata(db: Session, song_ids: list[str]) -> Metadata:
    """song_id -> (title, artist) from song_embeddings (used for version de-duplication)."""
    ids = list(dict.fromkeys(str(s) for s in song_ids))
    if not ids:
        return {}
    try:
        rows = _run(db, """
            SELECT song_id, title, artist_name FROM song_embeddings
            WHERE song_id = ANY(:ids) AND title IS NOT NULL AND title <> song_id
        """, {"ids": ids})
        return {str(r.song_id): (r.title, r.artist_name) for r in rows}
    except Exception:
        logger.debug("stored_metadata lookup failed", exc_info=True)
        return {}


def nearest(db: Session, vec: np.ndarray, n: int, exclude_ids: Iterable[str] = ()) -> list[dict[str, Any]]:
    """pgvector cosine nearest neighbours, excluding IDs. Returns ranked song dicts."""
    if vec is None or n <= 0:
        return []
    norm = float(np.linalg.norm(vec))
    if not np.isfinite(norm) or norm == 0:
        return []
    exclude = list(dict.fromkeys(str(s) for s in exclude_ids)) or [""]
    try:
        rows = _run(db, """
            SELECT song_id, 1 - (embedding <=> CAST(:vec AS vector)) AS similarity
            FROM song_embeddings
            WHERE embedding IS NOT NULL AND NOT (song_id = ANY(:exclude))
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT :n
        """, {"vec": _vec_literal(vec / norm), "exclude": exclude, "n": int(n)})
        return [
            {"song_id": str(r.song_id), "score": round(max(0.0, float(r.similarity)), 4), "rank": i + 1}
            for i, r in enumerate(rows)
        ]
    except Exception:
        logger.warning("Embedding nearest-neighbour query failed", exc_info=True)
        return []


def vector_for_song(db: Session, song_id: str, title: str | None = None,
                    artist: str | None = None) -> np.ndarray | None:
    """Stored vector if present; otherwise embed title+artist on the fly (not persisted here)."""
    vec = stored_vectors(db, [song_id]).get(str(song_id))
    if vec is not None:
        return vec
    if not title or not title.strip() or title == song_id:
        return None
    try:
        from app.services.embedding_service import embed_song
        return _parse_vec(embed_song(title.strip(), (artist or "").strip() or None))
    except Exception:
        logger.debug("On-the-fly embedding failed", exc_info=True)
        return None


def similar_to_song(db: Session, song_id: str, n: int, exclude_ids: Iterable[str] = (),
                    title: str | None = None, artist: str | None = None) -> list[dict[str, Any]]:
    vec = vector_for_song(db, song_id, title, artist)
    if vec is None:
        return []
    exclude = set(str(s) for s in exclude_ids)
    exclude.add(str(song_id))
    return nearest(db, vec, n, exclude)


def taste_recommendations(db: Session, song_ids: list[str], weights: list[float], n: int,
                          exclude_ids: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Weighted average of stored embeddings of the given songs -> nearest neighbours."""
    vectors = stored_vectors(db, song_ids)
    picked, picked_w = [], []
    for sid, w in zip(song_ids, weights):
        vec = vectors.get(str(sid))
        if vec is not None and w > 0:
            picked.append(vec / (np.linalg.norm(vec) or 1.0))
            picked_w.append(float(w))
    if not picked:
        return []
    taste = np.average(np.vstack(picked), axis=0, weights=picked_w)
    return nearest(db, taste, n, exclude_ids)


# ── Catalog seeding ────────────────────────────────────────────────────────────

def seed_catalog_embeddings(catalog: dict[str, dict[str, Any]], batch_size: int = 32,
                            pause_sec: float = 2.0, max_rows: int = 5000) -> int:
    """
    Make sure every content-catalog song has a title+artist embedding, so the
    fallback can recommend catalog songs. Idempotent: only missing rows are
    embedded, and rows persist in PostgreSQL across restarts. Throttled to stay
    friendly to the free-tier embedding service.
    """
    from app.core.database import SessionLocal
    from app.services.embedding_service import embed_batch, song_to_text

    db = SessionLocal()
    written = 0
    try:
        ids = list(catalog.keys())
        existing = set()
        for i in range(0, len(ids), 500):
            rows = _run(db, """
                SELECT song_id FROM song_embeddings
                WHERE song_id = ANY(:ids) AND embedding IS NOT NULL AND title <> song_id
            """, {"ids": ids[i:i + 500]})
            existing.update(str(r.song_id) for r in rows)
        todo = [sid for sid in ids if sid not in existing][:max_rows]
        if not todo:
            logger.info("[EmbeddingSeed] All %d catalog songs already have embeddings.", len(ids))
            return 0
        logger.info("[EmbeddingSeed] Embedding %d catalog songs missing from song_embeddings.", len(todo))
        for i in range(0, len(todo), batch_size):
            chunk = []
            for sid in todo[i:i + batch_size]:
                meta = catalog.get(sid) or {}
                title = meta.get("title")
                if isinstance(title, str) and title.strip():
                    artist = meta.get("artist") if isinstance(meta.get("artist"), str) else None
                    chunk.append((sid, title.strip(), artist))
            if not chunk:
                continue
            vecs = embed_batch([song_to_text(t, a) for _, t, a in chunk])
            if vecs is None or len(vecs) != len(chunk):
                logger.warning("[EmbeddingSeed] Embedding batch failed; will retry on next startup.")
                break
            for (sid, title, artist), vec in zip(chunk, vecs):
                db.execute(text("""
                    INSERT INTO song_embeddings (song_id, title, artist_name, embedding)
                    VALUES (:sid, :title, :artist, CAST(:vec AS vector))
                    ON CONFLICT (song_id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        title = CASE WHEN song_embeddings.title = song_embeddings.song_id
                                     THEN EXCLUDED.title ELSE song_embeddings.title END,
                        artist_name = COALESCE(song_embeddings.artist_name, EXCLUDED.artist_name)
                """), {"sid": sid, "title": title[:1024], "artist": (artist or None) and artist[:1024],
                       "vec": _vec_literal(np.asarray(vec, dtype=np.float32))})
            db.commit()
            written += len(chunk)
            time.sleep(pause_sec)
        logger.info("[EmbeddingSeed] Stored %d catalog embeddings.", written)
        return written
    except Exception:
        db.rollback()
        logger.warning("[EmbeddingSeed] Seeding stopped early (stored %d); will resume next startup.",
                       written, exc_info=True)
        return written
    finally:
        db.close()


def start_catalog_seeding(catalog: dict[str, dict[str, Any]]) -> None:
    if os.environ.get("SEED_CATALOG_EMBEDDINGS", "true").lower() in ("0", "false", "no"):
        logger.info("[EmbeddingSeed] Disabled via SEED_CATALOG_EMBEDDINGS.")
        return
    threading.Thread(target=seed_catalog_embeddings, args=(dict(catalog),),
                     name="embedding-seed", daemon=True).start()
