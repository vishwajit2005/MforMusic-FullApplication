"""
Prometheus metrics for the MforMusic MLOps service.

This module is the single place that defines custom ``mformusic_*`` metrics and
the protected ``GET /metrics`` endpoint. HTTP request metrics (``http_requests_total``,
``http_request_duration_seconds`` ...) still come from prometheus-fastapi-instrumentator,
wired in ``app/main.py``.

Design rules
------------
* Low cardinality only. Every label value passes through ``_bounded`` against a
  fixed allow-list and falls back to ``"other"``. user_id, song_id, raw URLs,
  session ids and free-text interaction types are never used as labels.
* Metrics never change behaviour. Every ``record_*`` helper swallows its own errors.
* Model state (availability, active version, sizes) is read at scrape time by a
  collector, so it is always current and only the *active* version is exported.
* If ``prometheus_client`` is not installed the helpers become no-ops and
  ``/metrics`` answers 503, matching the old "instrumentator not installed" behaviour.

Access control
--------------
``GET /metrics`` requires ``Authorization: Bearer <METRICS_TOKEN>``. When
METRICS_TOKEN is unset or shorter than 16 characters the endpoint is disabled (503).
"""
from __future__ import annotations

import hmac
import logging
import time
from typing import Any, Callable, Optional

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised implicitly
    from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, Gauge, Histogram, generate_latest
    from prometheus_client.core import GaugeMetricFamily

    PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover
    PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain"
    REGISTRY = None

    class _Noop:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass

    def Counter(*args, **kwargs):  # noqa: N802
        return _Noop()

    Gauge = Histogram = Counter

    def generate_latest(*args, **kwargs):  # noqa: N802
        return b""

    GaugeMetricFamily = None


# ── Allowed label values (anything else becomes "other") ─────────────────────
MODELS = ("collaborative_filtering", "content_based")
MODES = ("for_you", "similar")
TIERS = ("content_based", "collaborative_filtering", "embedding_based", "popular", "cold_start", "error")
PRIMARY_TIERS = ("content_based", "collaborative_filtering")
FALLBACK_REASONS = (
    "no_history", "no_positive_history", "content_model_unavailable",
    "no_recent_catalog_match", "no_content_results", "primary_tier_empty",
)
CHANNELS = ("http", "kafka")
INTERACTION_TYPES = ("play", "skip", "like", "unlike", "download", "playlist_add")
INGEST_FAILURE_REASONS = ("validation", "database", "other")
RETRAIN_RESULTS = ("success", "failure", "skipped")
DB_OPERATIONS = ("select", "insert", "update", "delete", "ddl", "connect", "other")
DB_ERROR_CLASSES = ("operational", "integrity", "programming", "data", "other")
DEPENDENCIES = ("embedding_service", "mysql", "kafka", "other")
DEPENDENCY_OPERATIONS = ("encode", "query", "produce", "consume", "other")

MIN_TOKEN_LENGTH = 16


def _bounded(value: Any, allowed: tuple, default: str = "other") -> str:
    """Return ``value`` if it is in ``allowed`` else ``default`` (keeps label cardinality fixed)."""
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in allowed:
            return candidate
    return default


# ── Metric definitions ───────────────────────────────────────────────────────
_LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

RECOMMENDATION_REQUESTS = Counter(
    "mformusic_recommendation_requests_total",
    "Recommendation responses by mode (for_you|similar) and the tier that served them.",
    ["mode", "tier"],
)
RECOMMENDATION_SONGS_SERVED = Counter(
    "mformusic_recommendation_songs_served_total",
    "Individual songs served across recommendation responses by mode and tier.",
    ["mode", "tier"],
)
RECOMMENDED_PLAYS = Counter(
    "mformusic_recommended_plays_total",
    "Count of play events for songs previously served to the user as recommendations.",
)
RECOMMENDATION_FAILURES = Counter(
    "mformusic_recommendation_failures_total",
    "Recommendation handler failures (HTTP 500).",
    ["mode"],
)
RECOMMENDATION_FALLBACKS = Counter(
    "mformusic_recommendation_fallbacks_total",
    "For You responses not served by the configured primary tier, with the best-known reason.",
    ["primary_tier", "served_tier", "reason"],
)
RECOMMENDATION_DURATION = Histogram(
    "mformusic_recommendation_duration_seconds",
    "Time spent computing a recommendation response.",
    ["mode", "tier"],
    buckets=_LATENCY_BUCKETS,
)
RECOMMENDATION_SCORES = Histogram(
    "mformusic_recommendation_scores",
    "Score distribution of recommendations by serving tier (uncalibrated ranking scores).",
    ["mode", "tier"],
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.5, 2.0, 5.0, 10.0),
)
HTTP_ACTIVE_REQUESTS = Gauge(
    "mformusic_http_active_requests",
    "Number of currently active HTTP requests.",
    ["handler"],
)

MODEL_RETRAINS = Counter(
    "mformusic_model_retrains_total",
    "Model training attempts by outcome (success|failure|skipped).",
    ["model", "result"],
)
MODEL_RETRAIN_DURATION = Histogram(
    "mformusic_model_retrain_duration_seconds",
    "Duration of completed (success or failure) training runs.",
    ["model"],
    buckets=(0.5, 1, 5, 15, 30, 60, 120, 300, 600, 1800),
)
MODEL_LAST_RETRAIN_SUCCESS = Gauge(
    "mformusic_model_last_retrain_success_timestamp_seconds",
    "Unix time of the last successful training run (0 = none since process start).",
    ["model"],
)
MODEL_ARTIFACTS_LOADED = Gauge(
    "mformusic_model_artifacts_loaded_timestamp_seconds",
    "Unix time model artifacts were last loaded from disk (0 = never since process start).",
    ["model"],
)

TELEMETRY_EVENTS = Counter(
    "mformusic_telemetry_events_total",
    "Telemetry events received by this service, by channel, event type and result.",
    ["channel", "interaction_type", "result"],
)
TELEMETRY_FAILURES = Counter(
    "mformusic_telemetry_ingest_failures_total",
    "Telemetry events that could not be stored, by channel and failure class.",
    ["channel", "reason"],
)
TELEMETRY_DURATION = Histogram(
    "mformusic_telemetry_ingest_duration_seconds",
    "Time to validate and store one telemetry event.",
    ["channel"],
    buckets=_LATENCY_BUCKETS,
)
KAFKA_CONSUMER_ENABLED = Gauge(
    "mformusic_kafka_consumer_enabled", "1 if a Kafka consumer is configured for this process."
)
KAFKA_CONSUMER_CONNECTED = Gauge(
    "mformusic_kafka_consumer_connected", "1 while the Kafka consumer holds a broker connection."
)
KAFKA_CONSUMER_ERRORS = Counter(
    "mformusic_kafka_consumer_errors_total", "Kafka consumer connect/poll errors (it retries with back-off)."
)

DB_OPERATION_DURATION = Histogram(
    "mformusic_db_operation_duration_seconds",
    "SQL statement duration by operation type.",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
DB_ERRORS = Counter(
    "mformusic_db_errors_total",
    "SQL/connection errors by operation type and error class.",
    ["operation", "error"],
)
DEPENDENCY_DURATION = Histogram(
    "mformusic_dependency_duration_seconds",
    "Duration of external dependency calls.",
    ["dependency", "operation", "status"],
    buckets=_LATENCY_BUCKETS,
)
DEPENDENCY_ERRORS = Counter(
    "mformusic_dependency_errors_total",
    "Dependency call errors by dependency, operation and error class.",
    ["dependency", "operation", "error"],
)


def _initialise_series() -> None:
    """Create zero-valued series so dashboards show 0 instead of 'No data'."""
    for mode in MODES:
        RECOMMENDATION_FAILURES.labels(mode)
        for tier in TIERS:
            RECOMMENDATION_REQUESTS.labels(mode, tier)
            RECOMMENDATION_SONGS_SERVED.labels(mode, tier)
    RECOMMENDED_PLAYS.inc(0)
    for model in MODELS:
        MODEL_LAST_RETRAIN_SUCCESS.labels(model).set(0)
        MODEL_ARTIFACTS_LOADED.labels(model).set(0)
        for result in RETRAIN_RESULTS:
            MODEL_RETRAINS.labels(model, result)
    for channel in CHANNELS:
        for itype in INTERACTION_TYPES:
            for result in ("accepted", "failed"):
                TELEMETRY_EVENTS.labels(channel, itype, result)
        for reason in INGEST_FAILURE_REASONS:
            TELEMETRY_FAILURES.labels(channel, reason)
    for operation in DB_OPERATIONS:
        for error in DB_ERROR_CLASSES:
            DB_ERRORS.labels(operation, error)
    KAFKA_CONSUMER_ENABLED.set(0)
    KAFKA_CONSUMER_CONNECTED.set(0)
    HTTP_ACTIVE_REQUESTS.labels("all").set(0)


_initialise_series()


# ── Recording helpers (never raise) ──────────────────────────────────────────
def record_recommendation(
    mode: str,
    tier: Any,
    duration_s: Optional[float] = None,
    primary_tier: Optional[str] = None,
    fallback_reason: Optional[str] = None,
    songs_count: int = 0,
) -> None:
    try:
        mode_l, tier_l = _bounded(mode, MODES), _bounded(tier, TIERS)
        RECOMMENDATION_REQUESTS.labels(mode_l, tier_l).inc()
        if songs_count > 0:
            RECOMMENDATION_SONGS_SERVED.labels(mode_l, tier_l).inc(songs_count)
        if duration_s is not None:
            RECOMMENDATION_DURATION.labels(mode_l, tier_l).observe(max(0.0, duration_s))
        if primary_tier is not None and tier_l != primary_tier:
            RECOMMENDATION_FALLBACKS.labels(
                _bounded(primary_tier, PRIMARY_TIERS),
                tier_l,
                _bounded(fallback_reason, FALLBACK_REASONS, "primary_tier_empty"),
            ).inc()
    except Exception:  # pragma: no cover - metrics must never break serving
        logger.debug("record_recommendation failed", exc_info=True)


def record_recommended_play() -> None:
    """Increment count of plays for songs previously recommended by the service."""
    try:
        RECOMMENDED_PLAYS.inc()
    except Exception:
        logger.debug("record_recommended_play failed", exc_info=True)


def record_recommendation_failure(mode: str, duration_s: Optional[float] = None) -> None:
    try:
        mode_l = _bounded(mode, MODES)
        RECOMMENDATION_FAILURES.labels(mode_l).inc()
        if duration_s is not None:
            RECOMMENDATION_DURATION.labels(mode_l, "error").observe(max(0.0, duration_s))
    except Exception:  # pragma: no cover
        logger.debug("record_recommendation_failure failed", exc_info=True)


def record_recommendation_scores(mode: str, tier: Any, scores: list[float]) -> None:
    """Record distribution of recommendation scores produced by serving tier (uncalibrated ranking scores)."""
    try:
        mode_l, tier_l = _bounded(mode, MODES), _bounded(tier, TIERS)
        for s in scores:
            if isinstance(s, (int, float)):
                RECOMMENDATION_SCORES.labels(mode_l, tier_l).observe(float(s))
    except Exception:  # pragma: no cover
        logger.debug("record_recommendation_scores failed", exc_info=True)


def record_retrain(model: str, result: str, started: Optional[float] = None) -> None:
    """``started`` is a ``time.perf_counter()`` value; duration is recorded for success/failure only."""
    try:
        model_l, result_l = _bounded(model, MODELS), _bounded(result, RETRAIN_RESULTS, "failure")
        MODEL_RETRAINS.labels(model_l, result_l).inc()
        if started is not None and result_l in ("success", "failure"):
            MODEL_RETRAIN_DURATION.labels(model_l).observe(max(0.0, time.perf_counter() - started))
        if result_l == "success":
            MODEL_LAST_RETRAIN_SUCCESS.labels(model_l).set(time.time())
    except Exception:  # pragma: no cover
        logger.debug("record_retrain failed", exc_info=True)


def record_model_loaded(model: str) -> None:
    try:
        MODEL_ARTIFACTS_LOADED.labels(_bounded(model, MODELS)).set(time.time())
    except Exception:  # pragma: no cover
        logger.debug("record_model_loaded failed", exc_info=True)


def classify_ingest_error(exc: BaseException) -> str:
    """Map an exception to a bounded failure class: validation | database | other."""
    try:
        from pydantic import ValidationError

        if isinstance(exc, ValidationError):
            return "validation"
    except Exception:  # pragma: no cover
        pass
    if isinstance(exc, SQLAlchemyError):
        return "database"
    return "other"


def record_telemetry(
    channel: str,
    interaction_type: Any,
    ok: bool,
    duration_s: Optional[float] = None,
    failure: Optional[str] = None,
) -> None:
    try:
        channel_l = _bounded(channel, CHANNELS)
        TELEMETRY_EVENTS.labels(channel_l, _bounded(interaction_type, INTERACTION_TYPES), "accepted" if ok else "failed").inc()
        if duration_s is not None:
            TELEMETRY_DURATION.labels(channel_l).observe(max(0.0, duration_s))
        if not ok:
            TELEMETRY_FAILURES.labels(channel_l, _bounded(failure, INGEST_FAILURE_REASONS)).inc()
    except Exception:  # pragma: no cover
        logger.debug("record_telemetry failed", exc_info=True)


def set_kafka_enabled(enabled: bool) -> None:
    KAFKA_CONSUMER_ENABLED.set(1 if enabled else 0)


def set_kafka_connected(connected: bool) -> None:
    KAFKA_CONSUMER_CONNECTED.set(1 if connected else 0)


def record_kafka_error() -> None:
    KAFKA_CONSUMER_ERRORS.inc()


def record_dependency_call(
    dependency: str,
    operation: str,
    duration_s: Optional[float] = None,
    status: str = "success",
    error: Optional[str] = None,
) -> None:
    """Record duration and errors for calls to external/downstream dependencies."""
    try:
        dep_l = _bounded(dependency, DEPENDENCIES)
        op_l = _bounded(operation, DEPENDENCY_OPERATIONS)
        stat_l = "success" if status == "success" else "failure"
        if duration_s is not None:
            DEPENDENCY_DURATION.labels(dep_l, op_l, stat_l).observe(max(0.0, duration_s))
        if stat_l != "success":
            err_label = (error or "unknown")[:64].lower().replace(" ", "_")
            DEPENDENCY_ERRORS.labels(dep_l, op_l, err_label).inc()
    except Exception:  # pragma: no cover
        logger.debug("record_dependency_call failed", exc_info=True)


# ── Database instrumentation (SQLAlchemy engine events) ──────────────────────
_DB_VERBS = {
    "select": "select", "with": "select", "insert": "insert", "update": "update", "delete": "delete",
    "create": "ddl", "alter": "ddl", "drop": "ddl",
}


def _operation(statement: Optional[str]) -> str:
    """Classify SQL text into a fixed operation set. Statement text is never exported."""
    if not statement:
        return "connect"
    head = statement.lstrip().lstrip("(").split(None, 1)
    return _DB_VERBS.get(head[0].lower(), "other") if head else "other"


_DB_ERROR_NAMES = {
    "OperationalError": "operational", "IntegrityError": "integrity",
    "ProgrammingError": "programming", "DataError": "data",
}


def _error_class(exc: BaseException) -> str:
    """Classify by class name along the MRO: covers SQLAlchemy wrappers and DBAPI errors
    (sqlite3/psycopg2), including subclasses such as psycopg2.errors.UndefinedTable."""
    for cls in type(exc).__mro__:
        name = _DB_ERROR_NAMES.get(cls.__name__)
        if name:
            return name
    return "other"


def instrument_engine(engine) -> None:
    """Record duration and errors of every SQL statement executed through ``engine`` (idempotent)."""
    if getattr(engine, "_mformusic_instrumented", False):
        return
    engine._mformusic_instrumented = True

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("mformusic_query_start", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        try:
            starts = conn.info.get("mformusic_query_start")
            if starts:
                DB_OPERATION_DURATION.labels(_operation(statement)).observe(time.perf_counter() - starts.pop())
        except Exception:  # pragma: no cover
            logger.debug("db duration metric failed", exc_info=True)

    @event.listens_for(engine, "handle_error")
    def _error(exception_context):
        try:
            conn = exception_context.connection
            if conn is not None:
                starts = conn.info.get("mformusic_query_start")
                if starts:
                    starts.pop()
            DB_ERRORS.labels(
                _operation(exception_context.statement),
                _error_class(exception_context.sqlalchemy_exception or exception_context.original_exception),
            ).inc()
        except Exception:  # pragma: no cover
            logger.debug("db error metric failed", exc_info=True)


# ── Scrape-time collectors ───────────────────────────────────────────────────
class _ModelStateCollector:
    """Exports current model availability/version/size by asking the live engines at scrape time."""

    def __init__(self, cf: Callable[[], dict], content: Callable[[], dict], priority: Callable[[], str]):
        self._providers = (("collaborative_filtering", cf), ("content_based", content))
        self._priority = priority

    def describe(self):
        return []

    def collect(self):
        available = GaugeMetricFamily(
            "mformusic_model_available", "1 if the model is loaded and able to serve requests.", labels=["model"])
        info = GaugeMetricFamily(
            "mformusic_model_info", "Currently active model version (value is always 1).", labels=["model", "version"])
        retraining = GaugeMetricFamily(
            "mformusic_model_retraining_in_progress", "1 while a retrain is running.", labels=["model"])
        items = GaugeMetricFamily(
            "mformusic_model_items", "Size of the data behind the active model.", labels=["model", "kind"])
        for model, provider in self._providers:
            try:
                stats = provider() or {}
            except Exception:
                logger.debug("model stats unavailable for %s", model, exc_info=True)
                continue
            ready = bool(stats.get("trained", stats.get("ready", False)))
            available.add_metric([model], 1.0 if ready else 0.0)
            info.add_metric([model, str(stats.get("model_version", "unknown"))[:64]], 1.0)
            retraining.add_metric([model], 1.0 if stats.get("retraining") else 0.0)
            last_trained = stats.get("last_trained_timestamp", 0.0)
            if last_trained and float(last_trained) > 0:
                MODEL_LAST_RETRAIN_SUCCESS.labels(model).set(float(last_trained))
            for kind, key in (("interactions", "total_interactions"), ("users", "total_users"),
                              ("songs", "total_songs"), ("tracks", "total_tracks")):
                if isinstance(stats.get(key), (int, float)):
                    items.add_metric([model, kind], float(stats[key]))
        yield available
        yield info
        yield retraining
        yield items
        try:
            priority = GaugeMetricFamily(
                "mformusic_recommendation_priority_info",
                "Configured serving priority (value is always 1).", labels=["priority"])
            priority.add_metric([_bounded(self._priority(), ("content_first", "cf_first"), "unknown")], 1.0)
            yield priority
        except Exception:  # pragma: no cover
            logger.debug("priority info unavailable", exc_info=True)


class _PoolCollector:
    def __init__(self, engine):
        self._engine = engine

    def describe(self):
        return []

    def collect(self):
        family = GaugeMetricFamily(
            "mformusic_db_pool_connections", "SQLAlchemy connection pool usage.", labels=["state"])
        pool = self._engine.pool
        for state, method in (("size", "size"), ("checked_out", "checkedout"),
                              ("checked_in", "checkedin"), ("overflow", "overflow")):
            try:
                value = float(getattr(pool, method)())
                if state == "overflow":
                    value = max(0.0, value)  # SQLAlchemy reports a negative number until the pool has grown
                family.add_metric([state], value)
            except Exception:
                continue
        yield family


_registered: set[str] = set()


def _register_once(key: str, collector) -> None:
    if not PROMETHEUS_AVAILABLE or key in _registered:
        return
    REGISTRY.register(collector)
    _registered.add(key)


def register_model_collector(cf: Callable[[], dict], content: Callable[[], dict], priority: Callable[[], str]) -> None:
    _register_once("models", _ModelStateCollector(cf, content, priority))


def register_pool_collector(engine) -> None:
    _register_once("db_pool", _PoolCollector(engine))


# ── Protected /metrics endpoint ──────────────────────────────────────────────
router = APIRouter()


@router.get("/metrics", include_in_schema=False)
def metrics_endpoint(request: Request) -> Response:
    if not PROMETHEUS_AVAILABLE:
        return PlainTextResponse("prometheus_client is not installed.\n", status_code=503)

    # Allow X-MforMusic-Key
    api_key = getattr(get_settings(), "MLOPS_API_KEY", "") or ""
    provided_key = request.headers.get("x-mformusic-key", "").strip()
    if api_key and provided_key and hmac.compare_digest(provided_key.encode(), api_key.encode()):
        return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

    token = (get_settings().METRICS_TOKEN or "").strip()
    if len(token) < MIN_TOKEN_LENGTH:
        return PlainTextResponse(
            f"Metrics endpoint disabled: set METRICS_TOKEN (at least {MIN_TOKEN_LENGTH} characters).\n",
            status_code=503,
        )
    scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(supplied.strip().encode(), token.encode()):
        return PlainTextResponse("Unauthorized\n", status_code=401, headers={"WWW-Authenticate": "Bearer"})
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
