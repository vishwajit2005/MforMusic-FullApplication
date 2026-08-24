import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── SQLAlchemy engine ─────────────────────────────────────────────────────────
# pool_pre_ping=True validates connections before use (handles Aiven/Render timeouts)
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Declarative base ──────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── pgvector extension & HNSW index ──────────────────────────────────────────
def ensure_pgvector_extension() -> bool:
    """
    Attempts to enable the pgvector extension.
    Fails gracefully if not supported — CF still works without it.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        logger.info("pgvector extension is enabled.")
        return True
    except Exception as e:
        logger.warning(
            f"pgvector extension not available (non-critical — CF works without it): {e}"
        )
        return False


def ensure_song_embeddings_hnsw_index() -> bool:
    """
    Creates the HNSW index on song_embeddings.embedding using vector_cosine_ops
    to enable sub-millisecond approximate nearest neighbor semantic search.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_song_embeddings_hnsw 
                ON song_embeddings 
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """))
            conn.commit()
        logger.info("HNSW cosine index on song_embeddings.embedding is ready ✓")
        return True
    except Exception as e:
        logger.warning(f"Could not create/verify HNSW index on song_embeddings: {e}")
        return False


# ── Dependency for FastAPI route injection ────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
