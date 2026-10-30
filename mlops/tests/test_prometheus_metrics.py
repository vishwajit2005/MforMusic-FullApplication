"""Prometheus metrics: label safety, protected /metrics, recorders, collectors, DB instrumentation."""
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY, CollectorRegistry, generate_latest
from sqlalchemy import create_engine, text

from app.core import metrics as m

TOKEN = "t" * 32


def sample(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


class TestLabelSafety(unittest.TestCase):
    def test_bounded_maps_unknown_values_to_default(self):
        self.assertEqual(m._bounded("play", m.INTERACTION_TYPES), "play")
        self.assertEqual(m._bounded(" PLAY ", m.INTERACTION_TYPES), "play")
        self.assertEqual(m._bounded("user-98765", m.INTERACTION_TYPES), "other")
        self.assertEqual(m._bounded(None, m.INTERACTION_TYPES), "other")
        self.assertEqual(m._bounded(42, m.TIERS), "other")

    def test_free_text_never_becomes_a_label_value(self):
        m.record_telemetry("http", "song_8f3a2c-secret-id", True, 0.01)
        m.record_telemetry("totally-new-channel", "play", False, 0.01, failure="boom: user 12345")
        text_out = generate_latest(REGISTRY).decode()
        for leaked in ("song_8f3a2c-secret-id", "totally-new-channel", "user 12345"):
            self.assertNotIn(leaked, text_out)

    def test_classify_ingest_error(self):
        from pydantic import BaseModel, ValidationError
        from sqlalchemy.exc import OperationalError

        class M(BaseModel):
            x: int

        with self.assertRaises(ValidationError) as ctx:
            M(x="not-an-int")
        self.assertEqual(m.classify_ingest_error(ctx.exception), "validation")
        self.assertEqual(m.classify_ingest_error(OperationalError("s", {}, Exception("d"))), "database")
        self.assertEqual(m.classify_ingest_error(RuntimeError("x")), "other")


class TestMetricsEndpoint(unittest.TestCase):
    def client(self, token):
        app = FastAPI()
        app.include_router(m.router)
        settings = type("S", (), {"METRICS_TOKEN": token})()
        patcher = patch.object(m, "get_settings", return_value=settings)
        patcher.start()
        self.addCleanup(patcher.stop)
        return TestClient(app)

    def test_disabled_without_or_with_short_token(self):
        for token in ("", "short"):
            self.assertEqual(self.client(token).get("/metrics").status_code, 503)

    def test_requires_matching_bearer_token(self):
        c = self.client(TOKEN)
        self.assertEqual(c.get("/metrics").status_code, 401)
        self.assertEqual(c.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code, 401)
        self.assertEqual(c.get("/metrics", headers={"Authorization": f"Basic {TOKEN}"}).status_code, 401)
        self.assertEqual(c.get("/metrics?token=" + TOKEN).status_code, 401)
        ok = c.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual(ok.status_code, 200)
        self.assertIn("mformusic_recommendation_requests_total", ok.text)
        self.assertEqual(c.get("/metrics").headers.get("www-authenticate"), "Bearer")


class TestRecorders(unittest.TestCase):
    def test_recommendation_counts_and_fallbacks(self):
        before = sample("mformusic_recommendation_requests_total", mode="for_you", tier="popular")
        fb = lambda served, reason: sample(  # noqa: E731
            "mformusic_recommendation_fallbacks_total", primary_tier="content_based", served_tier=served, reason=reason)
        b1, b2 = fb("popular", "no_history"), fb("collaborative_filtering", "primary_tier_empty")
        m.record_recommendation("for_you", "popular", 0.02, primary_tier="content_based", fallback_reason="no_history")
        m.record_recommendation("for_you", "collaborative_filtering", 0.02, primary_tier="content_based")
        m.record_recommendation("for_you", "content_based", 0.02, primary_tier="content_based")  # no fallback
        self.assertEqual(sample("mformusic_recommendation_requests_total", mode="for_you", tier="popular"), before + 1)
        self.assertEqual(fb("popular", "no_history"), b1 + 1)
        self.assertEqual(fb("collaborative_filtering", "primary_tier_empty"), b2 + 1)
        self.assertEqual(fb("content_based", "primary_tier_empty"), 0.0)

    def test_recommendation_failure(self):
        before = sample("mformusic_recommendation_failures_total", mode="similar")
        m.record_recommendation_failure("similar", 0.5)
        self.assertEqual(sample("mformusic_recommendation_failures_total", mode="similar"), before + 1)

    def test_retrain_outcomes(self):
        model = "collaborative_filtering"
        s0, f0, k0 = (sample("mformusic_model_retrains_total", model=model, result=r) for r in ("success", "failure", "skipped"))
        d0 = sample("mformusic_model_retrain_duration_seconds_count", model=model)
        m.record_retrain(model, "skipped")
        m.record_retrain(model, "failure", m.time.perf_counter())
        m.record_retrain(model, "success", m.time.perf_counter())
        self.assertEqual(sample("mformusic_model_retrains_total", model=model, result="success"), s0 + 1)
        self.assertEqual(sample("mformusic_model_retrains_total", model=model, result="failure"), f0 + 1)
        self.assertEqual(sample("mformusic_model_retrains_total", model=model, result="skipped"), k0 + 1)
        self.assertEqual(sample("mformusic_model_retrain_duration_seconds_count", model=model), d0 + 2)  # not for skipped
        self.assertGreater(sample("mformusic_model_last_retrain_success_timestamp_seconds", model=model), 1e9)

    def test_telemetry_success_and_failure(self):
        a0 = sample("mformusic_telemetry_events_total", channel="kafka", interaction_type="like", result="accepted")
        f0 = sample("mformusic_telemetry_ingest_failures_total", channel="kafka", reason="database")
        m.record_telemetry("kafka", "like", True, 0.01)
        m.record_telemetry("kafka", "like", False, 0.01, failure="database")
        self.assertEqual(sample("mformusic_telemetry_events_total", channel="kafka", interaction_type="like", result="accepted"), a0 + 1)
        self.assertEqual(sample("mformusic_telemetry_ingest_failures_total", channel="kafka", reason="database"), f0 + 1)

    def test_recommended_plays_and_songs_served(self):
        served_before = sample("mformusic_recommendation_songs_served_total", mode="for_you", tier="content_based")
        m.record_recommendation("for_you", "content_based", 0.02, songs_count=15)
        self.assertEqual(
            sample("mformusic_recommendation_songs_served_total", mode="for_you", tier="content_based"),
            served_before + 15,
        )

        rec_plays_before = sample("mformusic_recommended_plays_total")
        m.record_recommended_play()
        self.assertEqual(sample("mformusic_recommended_plays_total"), rec_plays_before + 1)

    def test_recommendation_impression_attribution(self):
        from app.services.recommendation_service import record_served_recommendation_ids, is_recommended_song
        record_served_recommendation_ids("user_test_42", ["song_a", "song_b"])
        self.assertTrue(is_recommended_song("user_test_42", "song_a"))
        self.assertTrue(is_recommended_song("user_test_42", "song_b"))
        self.assertFalse(is_recommended_song("user_test_42", "song_c"))
        self.assertFalse(is_recommended_song("user_test_99", "song_a"))


class TestCollectors(unittest.TestCase):
    def test_model_state_collector_exports_only_current_version(self):
        stats = {"trained": True, "model_version": "v_1i_2u_3s", "total_interactions": 1, "total_users": 2, "total_songs": 3, "retraining": False}
        content = {"ready": False, "model_version": "content_knn_uninitialized", "total_tracks": 0, "retraining": True}
        registry = CollectorRegistry()
        registry.register(m._ModelStateCollector(lambda: stats, lambda: content, lambda: "content_first"))
        out = generate_latest(registry).decode()
        self.assertIn('mformusic_model_available{model="collaborative_filtering"} 1.0', out)
        self.assertIn('mformusic_model_available{model="content_based"} 0.0', out)
        self.assertIn('mformusic_model_info{model="collaborative_filtering",version="v_1i_2u_3s"} 1.0', out)
        self.assertIn('mformusic_model_retraining_in_progress{model="content_based"} 1.0', out)
        self.assertIn('mformusic_model_items{kind="users",model="collaborative_filtering"} 2.0', out)
        self.assertIn('mformusic_recommendation_priority_info{priority="content_first"} 1.0', out)
        stats["model_version"] = "v_9i_9u_9s"          # a retrain swaps the version
        out = generate_latest(registry).decode()
        self.assertNotIn("v_1i_2u_3s", out)             # the old version series disappears
        self.assertIn("v_9i_9u_9s", out)

    def test_failing_provider_does_not_break_scrape(self):
        def boom():
            raise RuntimeError("locked")
        registry = CollectorRegistry()
        registry.register(m._ModelStateCollector(boom, lambda: {"ready": True, "model_version": "c"}, lambda: "cf_first"))
        out = generate_latest(registry).decode()
        self.assertIn('mformusic_model_available{model="content_based"} 1.0', out)
        self.assertNotIn('model="collaborative_filtering"', out)


class TestDatabaseInstrumentation(unittest.TestCase):
    def test_duration_and_errors_by_operation(self):
        engine = create_engine("sqlite://")
        m.instrument_engine(engine)
        m.instrument_engine(engine)  # idempotent: must not double count
        i0 = sample("mformusic_db_operation_duration_seconds_count", operation="insert")
        s0 = sample("mformusic_db_operation_duration_seconds_count", operation="select")
        d0 = sample("mformusic_db_operation_duration_seconds_count", operation="ddl")
        e0 = sample("mformusic_db_errors_total", operation="select", error="operational")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE t (id INTEGER)"))
            conn.execute(text("INSERT INTO t VALUES (1)"))
            conn.execute(text("SELECT * FROM t"))
        with self.assertRaises(Exception):
            with engine.connect() as conn:
                conn.execute(text("SELECT * FROM missing_table"))
        self.assertEqual(sample("mformusic_db_operation_duration_seconds_count", operation="ddl"), d0 + 1)
        self.assertEqual(sample("mformusic_db_operation_duration_seconds_count", operation="insert"), i0 + 1)
        self.assertEqual(sample("mformusic_db_operation_duration_seconds_count", operation="select"), s0 + 1)
        self.assertEqual(sample("mformusic_db_errors_total", operation="select", error="operational"), e0 + 1)
        self.assertNotIn("missing_table", generate_latest(REGISTRY).decode())  # SQL text is never exported

    def test_pool_collector_clamps_overflow_and_reports_usage(self):
        engine = create_engine("sqlite:////tmp/mformusic_pool_test.db", pool_size=5, max_overflow=10)  # QueuePool, like database.py
        registry = CollectorRegistry()
        registry.register(m._PoolCollector(engine))
        conn = engine.connect()
        out = generate_latest(registry).decode()
        conn.close()
        self.assertIn('mformusic_db_pool_connections{state="size"} 5.0', out)
        self.assertIn('mformusic_db_pool_connections{state="checked_out"} 1.0', out)
        self.assertIn('mformusic_db_pool_connections{state="overflow"} 0.0', out)  # raw SQLAlchemy value is negative here

    def test_db_error_series_exist_at_zero_for_dashboards(self):
        self.assertIsNotNone(REGISTRY.get_sample_value("mformusic_db_errors_total", {"operation": "select", "error": "operational"}))

    def test_operation_classification(self):
        for sql, op in [("SELECT 1", "select"), ("  with x as (select 1) select * from x", "select"),
                        ("INSERT INTO a", "insert"), ("UPDATE a", "update"), ("DELETE FROM a", "delete"),
                        ("CREATE INDEX i", "ddl"), ("VACUUM", "other"), (None, "connect"), ("", "connect")]:
            self.assertEqual(m._operation(sql), op, sql)


class TestCloudAuthWrapper(unittest.TestCase):
    """Deployed service: /metrics needs only its own bearer token; every other path still needs the shared key."""

    SHARED_KEY = "k" * 32

    def setUp(self):
        import os
        from app.deployment.auth import ServiceAuth

        app = FastAPI()
        app.include_router(m.router)

        @app.get("/health")
        def health():
            return {"ok": True}

        @app.get("/api/v1/private")
        def private():
            return {"secret": True}

        with patch.dict(os.environ, {"MLOPS_API_KEY": self.SHARED_KEY}):
            self.client = TestClient(ServiceAuth(app))
        patcher = patch.object(m, "get_settings", return_value=type("S", (), {"METRICS_TOKEN": TOKEN})())
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_metrics_needs_only_its_own_bearer_token(self):
        self.assertEqual(self.client.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"}).status_code, 200)
        self.assertEqual(self.client.get("/metrics").status_code, 401)  # rejected by /metrics itself
        self.assertEqual(self.client.get("/metrics", headers={"X-MforMusic-Key": self.SHARED_KEY}).status_code, 401)

    def test_metrics_token_does_not_unlock_the_api(self):
        self.assertEqual(self.client.get("/api/v1/private").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/private", headers={"Authorization": f"Bearer {TOKEN}"}).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/private", headers={"X-MforMusic-Key": self.SHARED_KEY}).status_code, 200)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_metrics_stays_closed_without_a_configured_token(self):
        with patch.object(m, "get_settings", return_value=type("S", (), {"METRICS_TOKEN": ""})()):
            self.assertEqual(self.client.get("/metrics", headers={"Authorization": "Bearer "}).status_code, 503)
            self.assertEqual(self.client.get("/metrics").status_code, 503)

    def test_recommendation_scores_distribution(self):
        m.record_recommendation_scores("for_you", "collaborative_filtering", [0.45, 0.85, 1.2])
        count = sample("mformusic_recommendation_scores_count", mode="for_you", tier="collaborative_filtering")
        self.assertGreaterEqual(count, 3.0)

    def test_dependency_call_tracking(self):
        m.record_dependency_call("embedding_service", "encode", 0.05, status="success")
        m.record_dependency_call("embedding_service", "encode", 0.12, status="failure", error="ConnectTimeout")
        
        ok_count = sample("mformusic_dependency_duration_seconds_count", dependency="embedding_service", operation="encode", status="success")
        err_count = sample("mformusic_dependency_errors_total", dependency="embedding_service", operation="encode", error="connecttimeout")
        self.assertGreaterEqual(ok_count, 1.0)
        self.assertGreaterEqual(err_count, 1.0)


if __name__ == "__main__":
    unittest.main()
