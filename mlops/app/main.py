"""
MforMusic MLOps Recommendation Engine
FastAPI application entry point.

Startup sequence:
  1. Create/verify PostgreSQL tables (via Hibernate-style auto-DDL)
  2. Enable pgvector extension (graceful fallback if unavailable)
  3. Initial CF model training from stored interactions
  4. Start APScheduler for hourly periodic retraining

Endpoints:
  POST /api/v1/interactions/ingest      ← Spring Boot forwards telemetry here
  GET  /api/v1/recommendations/{userId} ← Spring Boot proxies this to Android
  GET  /api/v1/recommendations/model/status
  POST /api/v1/recommendations/model/retrain
  GET  /health
"""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import interactions, recommendations
from app.api.v1 import search as search_router
from app.api.v1 import content as content_router
from app.consumers.kafka_consumer import get_kafka_consumer
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine, ensure_pgvector_extension, ensure_song_embeddings_hnsw_index
from app.models.interaction import Interaction          # noqa: F401 — ensures table is created
from app.models.song_embedding import SongEmbedding     # noqa: F401 — ensures table is created
from app.models.song_audio_feature import SongAudioFeature # noqa: F401 — ensures table is created
from app.services.cf_engine import cf_engine
from app.services.content_recommendation_service import content_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


# ── Periodic retrain jobs (called by APScheduler) ─────────────────────────────
def _scheduled_cf_retrain():
    logger.info("[Scheduler] Hourly CF retrain job triggered.")
    db = SessionLocal()
    try:
        cf_engine.train(db)
    except Exception as e:
        logger.error(f"[Scheduler] CF retrain failed: {e}")
    finally:
        db.close()


def _scheduled_content_retrain():
    logger.info("[Scheduler] Scheduled Content-based model retrain job triggered.")
    db = SessionLocal()
    try:
        content_service.train(db, force=False)
    except Exception as e:
        logger.error(f"[Scheduler] Content retrain failed: {e}")
    finally:
        db.close()


# ── Application lifespan ──────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info("=== MforMusic MLOps Service starting up ===")

    # 1. Enable pgvector (non-critical — CF works without it)
    has_vector = ensure_pgvector_extension()

    # 2. Create database tables
    try:
        Interaction.__table__.create(bind=engine, checkfirst=True)
        SongAudioFeature.__table__.create(bind=engine, checkfirst=True)
        if has_vector:
            SongEmbedding.__table__.create(bind=engine, checkfirst=True)
            ensure_song_embeddings_hnsw_index()
        logger.info("PostgreSQL tables created/verified.")
    except Exception as e:
        logger.warning(f"Table creation note: {e}")

    # 3. Initial model training
    db = SessionLocal()
    try:
        trained = cf_engine.train(db)
        if trained:
            logger.info(f"Initial CF model ready: {cf_engine.model_version}")
        else:
            logger.info(
                "No interaction data yet — model will train after first "
                f"{settings.RETRAIN_EVERY_N_INTERACTIONS} interactions are ingested."
            )
    finally:
        db.close()

    # 4. Retrain schedulers (CF hourly, Content model configurable)
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _scheduled_cf_retrain,
        trigger="interval",
        seconds=settings.RETRAIN_INTERVAL_SECONDS,
        id="hourly_cf_retrain",
        name="Hourly CF Model Retrain",
        replace_existing=True,
    )
    scheduler.add_job(
        _scheduled_content_retrain,
        trigger="interval",
        seconds=settings.CONTENT_RETRAIN_INTERVAL_SECONDS,
        id="content_model_retrain",
        name="Content Model Retrain",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        f"Retrain schedulers started — CF every {settings.RETRAIN_INTERVAL_SECONDS}s, "
        f"Content Model every {settings.CONTENT_RETRAIN_INTERVAL_SECONDS}s."
    )

    # 5. Load Content-Based Recommendation Model Artifacts
    try:
        content_loaded = content_service.load_artifacts(settings.CONTENT_MODEL_DIR)
        if content_loaded:
            logger.info(f"Content-based model ready: {content_service.model_version}")
        else:
            logger.info("Content-based model not loaded (artifacts missing or directory empty) — will use popular fallback.")
    except Exception as e:
        logger.warning(f"Content model startup loading failed: {e}")

    # 6. Kafka consumer — Phase 9 event-driven ingestion
    kafka_consumer = get_kafka_consumer()
    if kafka_consumer:
        kafka_consumer.start()

    yield

    # ── Shutdown ────────────────────────────────────────────────────
    if kafka_consumer:
        kafka_consumer.stop()
    scheduler.shutdown(wait=False)
    logger.info("=== MforMusic MLOps Service shut down ===")


# ── FastAPI application ───────────────────────────────────────────────────────
app = FastAPI(
    title="MforMusic MLOps Recommendation Engine",
    description=(
        "Collaborative Filtering & Content-based Similarity microservice for the MforMusic platform. "
        "Ingests telemetry and audio streams, serves personalized track recommendations and semantic search."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus Metrics (Phase 8) ──────────────────────────────────────────────
# Exposes GET /metrics — scraped by Prometheus every 10s
# Metrics: request counts, latency histograms, in-flight requests
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    logger.info("Prometheus /metrics endpoint registered ✓")
except ImportError:
    logger.warning("prometheus-fastapi-instrumentator not installed — /metrics unavailable.")


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(
    interactions.router,
    prefix="/api/v1/interactions",
    tags=["Telemetry Ingestion"],
)
app.include_router(
    recommendations.router,
    prefix="/api/v1/recommendations",
    tags=["Recommendations"],
)
app.include_router(
    content_router.router,
    prefix="/api/v1/content",
    tags=["Content-Based Model"],
)
app.include_router(
    search_router.router,
    prefix="/api/v1/search",
    tags=["Semantic Search"],
)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "ok",
        "cf_model_trained": cf_engine.is_trained,
        "cf_model_version": cf_engine.model_version,
        "content_model_ready": content_service.is_ready,
        "content_model_version": content_service.model_version,
        # Keep backwards compatibility for health check clients
        "model_trained": cf_engine.is_trained,
        "model_version": cf_engine.model_version,
    }
