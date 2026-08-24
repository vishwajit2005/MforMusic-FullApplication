"""
Backfill & Migration Script for song_embeddings

1. Ensures pgvector extension is enabled and song_embeddings table is created.
2. Checks existing rows for corrupted/placeholder titles (e.g. title == song_id).
3. Backfills and populates song_embeddings from app/data/content_model/track_index.csv
   with human-readable titles, artist names, and 384-dim sentence-transformers embeddings.
4. Creates the HNSW cosine index for sub-millisecond vector similarity search.
5. Reports before and after statistics.
"""

import logging
import sys
from pathlib import Path

# Add mlops root to sys.path
mlops_root = Path(__file__).resolve().parent.parent.parent
if str(mlops_root) not in sys.path:
    sys.path.insert(0, str(mlops_root))

import pandas as pd
from sqlalchemy import text
from app.core.database import engine, SessionLocal, ensure_pgvector_extension, ensure_song_embeddings_hnsw_index
from app.models.song_embedding import SongEmbedding
from app.services.embedding_service import embed_batch, song_to_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("backfill")


def run_backfill():
    logger.info("=== Starting Song Embeddings Backfill & Migration ===")

    # 1. Ensure pgvector extension & table
    has_vector = ensure_pgvector_extension()
    if not has_vector:
        logger.error("pgvector is not available in PostgreSQL! Aborting.")
        return False

    SongEmbedding.__table__.create(bind=engine, checkfirst=True)

    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE song_embeddings ALTER COLUMN title TYPE VARCHAR(1024);"))
        conn.execute(text("ALTER TABLE song_embeddings ALTER COLUMN artist_name TYPE VARCHAR(1024);"))
        conn.commit()

    db = SessionLocal()
    try:
        # 2. Before stats
        total_before = db.query(SongEmbedding).count()
        placeholders_before = (
            db.query(SongEmbedding)
            .filter(SongEmbedding.title == SongEmbedding.song_id)
            .count()
        )
        logger.info(f"Stats BEFORE backfill: total_rows={total_before}, placeholder_titles={placeholders_before}")

        # 3. Load track index dataset
        track_index_path = mlops_root / "app" / "data" / "content_model" / "track_index.csv"
        if not track_index_path.exists():
            logger.error(f"track_index.csv not found at {track_index_path}")
            return False

        df = pd.read_csv(track_index_path)
        logger.info(f"Loaded {len(df)} tracks from {track_index_path}")

        # Identify columns
        id_col = "external_track_id" if "external_track_id" in df.columns else df.columns[0]
        title_col = "title" if "title" in df.columns else df.columns[1]
        artist_col = "artist" if "artist" in df.columns else (df.columns[2] if len(df.columns) > 2 else None)

        tracks_to_process = []
        for _, row in df.iterrows():
            song_id = str(row[id_col]).strip()
            title = str(row[title_col]).strip() if pd.notna(row[title_col]) else song_id
            artist = str(row[artist_col]).strip() if (artist_col and pd.notna(row[artist_col])) else None
            tracks_to_process.append((song_id, title, artist))

        # 4. Batch embed and upsert
        batch_size = 64
        logger.info(f"Generating embeddings and upserting in batches of {batch_size}...")

        upserted_count = 0
        for i in range(0, len(tracks_to_process), batch_size):
            batch = tracks_to_process[i:i + batch_size]
            texts_to_embed = [song_to_text(t[1], t[2]) for t in batch]
            vecs = embed_batch(texts_to_embed)

            if vecs is None:
                logger.error(f"Failed to generate embeddings for batch {i // batch_size}")
                continue

            for (song_id, title, artist), vec in zip(batch, vecs):
                existing = db.query(SongEmbedding).filter(SongEmbedding.song_id == song_id).first()
                if existing:
                    existing.title = title
                    existing.artist_name = artist
                    existing.embedding = vec.tolist()
                else:
                    new_rec = SongEmbedding(
                        song_id=song_id,
                        title=title,
                        artist_name=artist,
                        embedding=vec.tolist(),
                    )
                    db.add(new_rec)
                upserted_count += 1

            db.commit()
            logger.info(f"Processed {min(i + batch_size, len(tracks_to_process))}/{len(tracks_to_process)} tracks")

        # 5. Ensure HNSW index is created
        logger.info("Ensuring HNSW cosine index on song_embeddings...")
        ensure_song_embeddings_hnsw_index()

        # 6. After stats
        total_after = db.query(SongEmbedding).count()
        placeholders_after = (
            db.query(SongEmbedding)
            .filter(SongEmbedding.title == SongEmbedding.song_id)
            .count()
        )
        logger.info(f"Stats AFTER backfill: total_rows={total_after}, placeholder_titles={placeholders_after}")
        logger.info(f"Successfully backfilled {upserted_count} song embeddings with readable titles and HNSW index ✓")
        return True

    except Exception as e:
        logger.error(f"Backfill migration failed: {e}", exc_info=True)
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    run_backfill()
