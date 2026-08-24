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


# ── pgvector extension ────────────────────────────────────────────────────────
def ensure_pgvector_extension() -> bool:
    """
    Attempts to enable the pgvector extension.
    Fails gracefully if not supported — CF still works without it.
    pgvector is only needed for future content-based embedding similarity.
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


# ── Dependency for FastAPI route injection ────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
