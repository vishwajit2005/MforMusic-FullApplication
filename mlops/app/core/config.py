from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── PostgreSQL + pgvector ────────────────────────────────────────────────
    # For local dev: postgresql://postgres:postgres@localhost:5432/mlops_db
    # For production (Aiven / Render PostgreSQL): full connection string
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/mlops_db"

    # ── Collaborative Filtering hyper-parameters ─────────────────────────────
    # ALS latent factors — 64 is a solid default; increase for larger catalogs
    CF_FACTORS: int = 64
    # ALS training iterations — 50 converges well for < 100k interactions
    CF_ITERATIONS: int = 50
    # L2 regularization — prevents overfitting on sparse interaction matrices
    CF_REGULARIZATION: float = 0.01

    # ── Cold-start threshold ─────────────────────────────────────────────────
    # Users with fewer interactions than this get "popular songs" fallback
    MIN_INTERACTIONS_FOR_CF: int = 3

    # ── Auto-retrain trigger ─────────────────────────────────────────────────
    # Retrain the ALS model after every N new ingested interactions
    RETRAIN_EVERY_N_INTERACTIONS: int = 50
    # Also retrain on a fixed schedule (seconds). 3600 = hourly.
    RETRAIN_INTERVAL_SECONDS: int = 3600

    # ── Recommendation defaults ──────────────────────────────────────────────
    TOP_N_RECOMMENDATIONS: int = 20

    # ── Service ─────────────────────────────────────────────────────────────
    PORT: int = 8000

    model_config = {"env_file": ".env", "case_sensitive": True}


@lru_cache
def get_settings() -> Settings:
    return Settings()
