import json

def build_dashboard():
    panels = []
    
    # ── Section 1: Service Health ─────────────────────────────────────────────
    panels.append({
        "id": 100,
        "type": "row",
        "title": "1. Service Health",
        "collapsed": False,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0}
    })
    
    panels.append({
        "id": 1,
        "type": "stat",
        "title": "FastAPI (MLOps Engine)",
        "description": "Availability status of the FastAPI MLOps recommendation service. Scraped at /metrics with bearer token.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 4, "w": 4, "x": 0, "y": 1},
        "targets": [{"expr": "up{job=\"mformusic-mlops\"}", "refId": "A"}],
        "fieldConfig": {
            "defaults": {
                "noValue": "n/a",
                "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]},
                "mappings": [{"type": "value", "options": {"0": {"text": "DOWN", "color": "red"}, "1": {"text": "UP", "color": "green"}}}]
            }
        },
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "graphMode": "none"}
    })
    
    panels.append({
        "id": 2,
        "type": "stat",
        "title": "Spring Boot (REST API)",
        "description": "Availability status of the Spring Boot backend service. Scraped at /actuator/prometheus.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 4, "w": 4, "x": 4, "y": 1},
        "targets": [{"expr": "up{job=\"mformusic-backend\"}", "refId": "A"}],
        "fieldConfig": {
            "defaults": {
                "noValue": "n/a",
                "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]},
                "mappings": [{"type": "value", "options": {"0": {"text": "DOWN", "color": "red"}, "1": {"text": "UP", "color": "green"}}}]
            }
        },
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "graphMode": "none"}
    })
    
    panels.append({
        "id": 3,
        "type": "stat",
        "title": "Prometheus Scrape Status",
        "description": "Self-monitoring availability of the Prometheus scraper engine.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 4, "w": 4, "x": 8, "y": 1},
        "targets": [{"expr": "up{job=\"prometheus\"}", "refId": "A"}],
        "fieldConfig": {
            "defaults": {
                "noValue": "n/a",
                "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]},
                "mappings": [{"type": "value", "options": {"0": {"text": "DOWN", "color": "red"}, "1": {"text": "UP", "color": "green"}}}]
            }
        },
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "graphMode": "none"}
    })

    panels.append({
        "id": 4,
        "type": "stat",
        "title": "FastAPI Uptime",
        "description": "Current uptime duration for FastAPI process since last start or restart.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 4, "w": 4, "x": 12, "y": 1},
        "targets": [{"expr": "time() - process_start_time_seconds{job=\"mformusic-mlops\"}", "refId": "A"}],
        "fieldConfig": {"defaults": {"unit": "s", "noValue": "n/a"}},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value", "graphMode": "none"}
    })

    panels.append({
        "id": 5,
        "type": "stat",
        "title": "Spring Boot Uptime",
        "description": "Current uptime duration for Spring Boot JVM process.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 4, "w": 4, "x": 16, "y": 1},
        "targets": [{"expr": "process_uptime_seconds{job=\"mformusic-backend\"} or (time() - process_start_time_seconds{job=\"mformusic-backend\"})", "refId": "A"}],
        "fieldConfig": {"defaults": {"unit": "s", "noValue": "n/a"}},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value", "graphMode": "none"}
    })

    panels.append({
        "id": 6,
        "type": "stat",
        "title": "Process Restarts (24h)",
        "description": "Number of process restart events detected across services in the last 24 hours.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 4, "w": 4, "x": 20, "y": 1},
        "targets": [{"expr": "sum(resets(process_start_time_seconds[24h]))", "refId": "A"}],
        "fieldConfig": {
            "defaults": {
                "noValue": "0",
                "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "orange", "value": 1}, {"color": "red", "value": 3}]}
            }
        },
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value", "graphMode": "none"}
    })

    # ── Section 2: API Performance ───────────────────────────────────────────
    panels.append({
        "id": 200,
        "type": "row",
        "title": "2. API Performance",
        "collapsed": False,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 5}
    })

    panels.append({
        "id": 7,
        "type": "timeseries",
        "title": "API Request Rate by Route Template",
        "description": "Incoming requests per second grouped by route template (bounded cardinality, never raw URLs).",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 6},
        "targets": [
            {"expr": "sum by (handler) (rate(http_requests_total{job=\"mformusic-mlops\"}[5m]))", "refId": "A", "legendFormat": "FastAPI: {{handler}}"},
            {"expr": "sum by (uri) (rate(http_server_requests_seconds_count{job=\"mformusic-backend\"}[5m]))", "refId": "B", "legendFormat": "Spring: {{uri}}"}
        ],
        "fieldConfig": {"defaults": {"unit": "reqps", "custom": {"fillOpacity": 10, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    panels.append({
        "id": 8,
        "type": "timeseries",
        "title": "Active In-Flight Requests",
        "description": "Number of concurrent HTTP requests currently in progress.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 6},
        "targets": [
            {"expr": "sum by (handler) (mformusic_http_active_requests)", "refId": "A", "legendFormat": "{{handler}}"}
        ],
        "fieldConfig": {"defaults": {"unit": "short", "custom": {"fillOpacity": 15, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    panels.append({
        "id": 9,
        "type": "timeseries",
        "title": "Response Time Percentiles (p50, p95, p99)",
        "description": "HTTP latency percentiles across endpoints. Includes median (p50), 95th percentile, and 99th percentile.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 14},
        "targets": [
            {"expr": "histogram_quantile(0.50, sum by (le) (rate(http_request_duration_seconds_bucket{job=\"mformusic-mlops\"}[5m])))", "refId": "A", "legendFormat": "FastAPI p50"},
            {"expr": "histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job=\"mformusic-mlops\"}[5m])))", "refId": "B", "legendFormat": "FastAPI p95"},
            {"expr": "histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket{job=\"mformusic-mlops\"}[5m])))", "refId": "C", "legendFormat": "FastAPI p99"},
            {"expr": "histogram_quantile(0.95, sum by (le) (rate(http_server_requests_seconds_bucket{job=\"mformusic-backend\"}[5m])))", "refId": "D", "legendFormat": "Spring p95"}
        ],
        "fieldConfig": {"defaults": {"unit": "s", "custom": {"fillOpacity": 10, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    panels.append({
        "id": 10,
        "type": "timeseries",
        "title": "4xx Client Errors & 5xx Server Failures",
        "description": "Error rates grouped by service, route template and status code class.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 14},
        "targets": [
            {"expr": "sum by (handler, status) (rate(http_requests_total{job=\"mformusic-mlops\",status=~\"4xx|5xx\"}[5m]))", "refId": "A", "legendFormat": "FastAPI: {{handler}} ({{status}})"},
            {"expr": "sum by (uri, status) (rate(http_server_requests_seconds_count{job=\"mformusic-backend\",status=~\"[45].*\"}[5m]))", "refId": "B", "legendFormat": "Spring: {{uri}} ({{status}})"}
        ],
        "fieldConfig": {"defaults": {"unit": "reqps", "custom": {"fillOpacity": 10, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    # ── Section 3: Database and Interaction Writes ───────────────────────────
    panels.append({
        "id": 300,
        "type": "row",
        "title": "3. Database and Interaction Writes",
        "collapsed": False,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 22}
    })

    panels.append({
        "id": 11,
        "type": "gauge",
        "title": "Spring HikariCP Pool Usage",
        "description": "Percentage of MySQL connection pool in active use by Spring Boot.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 6, "x": 0, "y": 23},
        "targets": [
            {"expr": "(hikaricp_connections_active{job=\"mformusic-backend\"} / clamp_min(hikaricp_connections_max{job=\"mformusic-backend\"}, 1)) * 100", "refId": "A"}
        ],
        "fieldConfig": {
            "defaults": {
                "unit": "percent",
                "min": 0,
                "max": 100,
                "noValue": "0",
                "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "orange", "value": 70}, {"color": "red", "value": 85}]}
            }
        },
        "options": {"orientation": "auto", "showThresholdLabels": False, "showThresholdMarkers": True}
    })

    panels.append({
        "id": 12,
        "type": "gauge",
        "title": "FastAPI SQLAlchemy Pool Usage",
        "description": "Percentage of PostgreSQL connection pool checked out by FastAPI.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 6, "x": 6, "y": 23},
        "targets": [
            {"expr": "(mformusic_db_pool_connections{job=\"mformusic-mlops\",state=\"checked_out\"} / clamp_min(mformusic_db_pool_connections{job=\"mformusic-mlops\",state=\"size\"}, 1)) * 100", "refId": "A"}
        ],
        "fieldConfig": {
            "defaults": {
                "unit": "percent",
                "min": 0,
                "max": 100,
                "noValue": "0",
                "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "orange", "value": 70}, {"color": "red", "value": 85}]}
            }
        },
        "options": {"orientation": "auto", "showThresholdLabels": False, "showThresholdMarkers": True}
    })

    panels.append({
        "id": 13,
        "type": "timeseries",
        "title": "New Interaction Records Written / Minute",
        "description": "Aggregate volume of new interaction records persisted per minute. Kept strictly aggregate with no individual user/song IDs.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 12, "x": 12, "y": 23},
        "targets": [
            {"expr": "sum(rate(mformusic_interaction_write_records_total{job=\"mformusic-backend\",status=\"success\"}[1m])) * 60", "refId": "A", "legendFormat": "Spring (MySQL)"},
            {"expr": "sum(rate(mformusic_telemetry_events_total{job=\"mformusic-mlops\",result=\"accepted\"}[1m])) * 60", "refId": "B", "legendFormat": "FastAPI (PostgreSQL)"}
        ],
        "fieldConfig": {"defaults": {"unit": "records/min", "custom": {"fillOpacity": 15, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    panels.append({
        "id": 14,
        "type": "timeseries",
        "title": "DB Pool Connection States",
        "description": "Active, idle, and pending connections waiting for database pool slots.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 8, "x": 0, "y": 30},
        "targets": [
            {"expr": "hikaricp_connections_active{job=\"mformusic-backend\"}", "refId": "A", "legendFormat": "Hikari Active"},
            {"expr": "hikaricp_connections_idle{job=\"mformusic-backend\"}", "refId": "B", "legendFormat": "Hikari Idle"},
            {"expr": "hikaricp_connections_pending{job=\"mformusic-backend\"}", "refId": "C", "legendFormat": "Hikari Pending (Waiting)"},
            {"expr": "mformusic_db_pool_connections{job=\"mformusic-mlops\"}", "refId": "D", "legendFormat": "SQLAlchemy: {{state}}"}
        ],
        "fieldConfig": {"defaults": {"unit": "short", "custom": {"fillOpacity": 10, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    panels.append({
        "id": 15,
        "type": "timeseries",
        "title": "Interaction Write & Query Latency (p95)",
        "description": "95th percentile duration to validate and persist interactions or execute database operations.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 8, "x": 8, "y": 30},
        "targets": [
            {"expr": "histogram_quantile(0.95, sum by (le) (rate(mformusic_telemetry_ingest_duration_seconds_bucket[5m])))", "refId": "A", "legendFormat": "MLOps Ingest p95"},
            {"expr": "histogram_quantile(0.95, sum by (le, operation) (rate(mformusic_db_operation_duration_seconds_bucket[5m])))", "refId": "B", "legendFormat": "DB SQL p95: {{operation}}"}
        ],
        "fieldConfig": {"defaults": {"unit": "s", "custom": {"fillOpacity": 10, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    panels.append({
        "id": 16,
        "type": "timeseries",
        "title": "Database & Write Errors",
        "description": "Failures during database operations, connection acquisition timeouts, or telemetry persistence.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 8, "x": 16, "y": 30},
        "targets": [
            {"expr": "sum by (operation, error) (rate(mformusic_db_errors_total[5m]))", "refId": "A", "legendFormat": "DB SQL: {{operation}} ({{error}})"},
            {"expr": "sum by (error_type) (rate(mformusic_interaction_write_errors_total[5m]))", "refId": "B", "legendFormat": "Interaction Write: {{error_type}}"},
            {"expr": "rate(hikaricp_connections_timeout_total[5m])", "refId": "C", "legendFormat": "Hikari Timeout/s"}
        ],
        "fieldConfig": {"defaults": {"unit": "errps", "custom": {"fillOpacity": 10, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    # ── Section 4: Recommendation Reliability ────────────────────────────────
    panels.append({
        "id": 400,
        "type": "row",
        "title": "4. Recommendation Reliability",
        "collapsed": False,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 37}
    })

    panels.append({
        "id": 17,
        "type": "timeseries",
        "title": "Recommendation Failures & Timeouts",
        "description": "Handler errors and unexpected failures when generating recommendations.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 8, "x": 0, "y": 38},
        "targets": [
            {"expr": "sum by (mode) (rate(mformusic_recommendation_failures_total[5m]))", "refId": "A", "legendFormat": "Failures ({{mode}})"}
        ],
        "fieldConfig": {"defaults": {"unit": "failures/s", "custom": {"fillOpacity": 15, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    panels.append({
        "id": 18,
        "type": "timeseries",
        "title": "Total Fallback Rate (%)",
        "description": "Percentage of For You recommendation requests not satisfied by the primary model tier that fell back to alternative tiers.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 8, "x": 8, "y": 38},
        "targets": [
            {"expr": "(sum(rate(mformusic_recommendation_fallbacks_total[5m])) / clamp_min(sum(rate(mformusic_recommendation_requests_total{mode=\"for_you\"}[5m])), 0.001)) * 100", "refId": "A", "legendFormat": "Fallback Rate"}
        ],
        "fieldConfig": {"defaults": {"unit": "percent", "custom": {"fillOpacity": 15, "showPoints": "never"}, "min": 0, "max": 100}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    panels.append({
        "id": 19,
        "type": "timeseries",
        "title": "Fallbacks by Reason",
        "description": "Root causes for model fallbacks (no_history, no_positive_history, content_model_unavailable, etc.).",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 8, "x": 16, "y": 38},
        "targets": [
            {"expr": "sum by (reason) (rate(mformusic_recommendation_fallbacks_total[5m]))", "refId": "A", "legendFormat": "{{reason}}"}
        ],
        "fieldConfig": {"defaults": {"unit": "fallbacks/s", "custom": {"fillOpacity": 15, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    panels.append({
        "id": 20,
        "type": "timeseries",
        "title": "Recommendation Computation Latency (p95)",
        "description": "95th percentile duration to compute recommendation rankings.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 12, "x": 0, "y": 45},
        "targets": [
            {"expr": "histogram_quantile(0.95, sum by (le, mode) (rate(mformusic_recommendation_duration_seconds_bucket[5m])))", "refId": "A", "legendFormat": "{{mode}} p95"}
        ],
        "fieldConfig": {"defaults": {"unit": "s", "custom": {"fillOpacity": 10, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    panels.append({
        "id": 21,
        "type": "timeseries",
        "title": "Recommendation Request Rate",
        "description": "Incoming recommendation requests per second by mode.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 12, "x": 12, "y": 45},
        "targets": [
            {"expr": "sum by (mode) (rate(mformusic_recommendation_requests_total[5m]))", "refId": "A", "legendFormat": "{{mode}}"}
        ],
        "fieldConfig": {"defaults": {"unit": "reqps", "custom": {"fillOpacity": 10, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    # ── Section 5: Model Readiness ───────────────────────────────────────────
    panels.append({
        "id": 500,
        "type": "row",
        "title": "5. Model Readiness",
        "collapsed": False,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 52}
    })

    panels.append({
        "id": 22,
        "type": "stat",
        "title": "CF (ALS) Model Ready",
        "description": "Whether the Collaborative Filtering (implicit ALS) model is loaded and ready to serve.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 4, "w": 4, "x": 0, "y": 53},
        "targets": [{"expr": "mformusic_model_available{model=\"collaborative_filtering\"}", "refId": "A"}],
        "fieldConfig": {
            "defaults": {
                "noValue": "0",
                "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]},
                "mappings": [{"type": "value", "options": {"0": {"text": "NOT READY", "color": "red"}, "1": {"text": "READY", "color": "green"}}}]
            }
        },
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "graphMode": "none"}
    })

    panels.append({
        "id": 23,
        "type": "stat",
        "title": "Content (Audio KNN) Ready",
        "description": "Whether the Content-based recommendation model artifacts are loaded.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 4, "w": 4, "x": 4, "y": 53},
        "targets": [{"expr": "mformusic_model_available{model=\"content_based\"}", "refId": "A"}],
        "fieldConfig": {
            "defaults": {
                "noValue": "0",
                "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]},
                "mappings": [{"type": "value", "options": {"0": {"text": "NOT READY", "color": "red"}, "1": {"text": "READY", "color": "green"}}}]
            }
        },
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "graphMode": "none"}
    })

    panels.append({
        "id": 24,
        "type": "stat",
        "title": "CF Active Version",
        "description": "Active artifact version string for Collaborative Filtering model.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 4, "w": 4, "x": 8, "y": 53},
        "targets": [{"expr": "mformusic_model_info{model=\"collaborative_filtering\"}", "refId": "A"}],
        "fieldConfig": {"defaults": {"noValue": "n/a"}},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "/^version$/"}, "textMode": "value", "colorMode": "value"}
    })

    panels.append({
        "id": 25,
        "type": "stat",
        "title": "Content Active Version",
        "description": "Active artifact version string for Content-based model.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 4, "w": 4, "x": 12, "y": 53},
        "targets": [{"expr": "mformusic_model_info{model=\"content_based\"}", "refId": "A"}],
        "fieldConfig": {"defaults": {"noValue": "n/a"}},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "/^version$/"}, "textMode": "value", "colorMode": "value"}
    })

    panels.append({
        "id": 26,
        "type": "stat",
        "title": "Time Since Last Retrain",
        "description": "Elapsed seconds since the last successful background retraining run.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 4, "w": 4, "x": 16, "y": 53},
        "targets": [{"expr": "time() - mformusic_model_last_retrain_success_timestamp_seconds{model=\"collaborative_filtering\"}", "refId": "A"}],
        "fieldConfig": {"defaults": {"unit": "s", "noValue": "n/a"}},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value", "graphMode": "none"}
    })

    panels.append({
        "id": 27,
        "type": "stat",
        "title": "Retraining Status",
        "description": "Whether a model retraining job is actively executing right now.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 4, "w": 4, "x": 20, "y": 53},
        "targets": [{"expr": "sum(mformusic_model_retraining_in_progress)", "refId": "A"}],
        "fieldConfig": {
            "defaults": {
                "noValue": "0",
                "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "blue", "value": 1}]},
                "mappings": [{"type": "value", "options": {"0": {"text": "IDLE", "color": "green"}, "1": {"text": "TRAINING", "color": "blue"}}}]
            }
        },
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "graphMode": "none"}
    })

    panels.append({
        "id": 28,
        "type": "timeseries",
        "title": "Recommendation Score Distribution (by Tier)",
        "description": "Distribution of ranking scores produced by serving tier. Labeled as scores, not confidence probabilities.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 57},
        "targets": [
            {"expr": "sum by (tier) (rate(mformusic_recommendation_scores_count[5m]))", "refId": "A", "legendFormat": "{{tier}} scores evaluated/s"},
            {"expr": "sum by (tier) (rate(mformusic_recommendation_scores_sum[5m])) / clamp_min(sum by (tier) (rate(mformusic_recommendation_scores_count[5m])), 0.001)", "refId": "B", "legendFormat": "Average score ({{tier}})"}
        ],
        "fieldConfig": {"defaults": {"custom": {"fillOpacity": 10, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    panels.append({
        "id": 29,
        "type": "timeseries",
        "title": "Retrain Outcomes & Durations",
        "description": "Model training runs by outcome (success, failure, skipped) and completed training runtime duration.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 57},
        "targets": [
            {"expr": "sum by (model, result) (rate(mformusic_model_retrains_total[1h]))", "refId": "A", "legendFormat": "Runs/h: {{model}} ({{result}})"},
            {"expr": "mformusic_model_retrain_duration_seconds_sum / clamp_min(mformusic_model_retrain_duration_seconds_count, 1)", "refId": "B", "legendFormat": "Avg duration: {{model}}"}
        ],
        "fieldConfig": {"defaults": {"custom": {"fillOpacity": 10, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    # ── Section 6: Dependencies ──────────────────────────────────────────────
    panels.append({
        "id": 600,
        "type": "row",
        "title": "6. Dependencies",
        "collapsed": False,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 65}
    })

    panels.append({
        "id": 30,
        "type": "timeseries",
        "title": "External Music API (JioSaavn) Latency",
        "description": "Average response time for search and song lookup calls to mformusic-api / JioSaavn.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 8, "x": 0, "y": 66},
        "targets": [
            {"expr": "mformusic_dependency_call_duration_seconds_sum{dependency=\"external_music_api\"} / clamp_min(mformusic_dependency_call_duration_seconds_count{dependency=\"external_music_api\"}, 1)", "refId": "A", "legendFormat": "Avg Latency (s)"}
        ],
        "fieldConfig": {"defaults": {"unit": "s", "custom": {"fillOpacity": 10, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    panels.append({
        "id": 31,
        "type": "timeseries",
        "title": "External Music API Errors & Timeouts",
        "description": "Rate of failures, timeouts, and non-2xx responses from external music catalogue.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 8, "x": 8, "y": 66},
        "targets": [
            {"expr": "sum by (operation, error_type) (rate(mformusic_dependency_call_errors_total{dependency=\"external_music_api\"}[5m]))", "refId": "A", "legendFormat": "{{operation}}: {{error_type}}"}
        ],
        "fieldConfig": {"defaults": {"unit": "errps", "custom": {"fillOpacity": 10, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    panels.append({
        "id": 32,
        "type": "timeseries",
        "title": "FastAPI Dependency Latency (from Backend)",
        "description": "Round-trip HTTP latency from Spring Boot to FastAPI recommendation engine.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 8, "x": 16, "y": 66},
        "targets": [
            {"expr": "mformusic_dependency_call_duration_seconds_sum{dependency=\"fastapi\"} / clamp_min(mformusic_dependency_call_duration_seconds_count{dependency=\"fastapi\"}, 1)", "refId": "A", "legendFormat": "Avg Latency (s)"}
        ],
        "fieldConfig": {"defaults": {"unit": "s", "custom": {"fillOpacity": 10, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    panels.append({
        "id": 33,
        "type": "timeseries",
        "title": "FastAPI Dependency Errors & Timeouts",
        "description": "Errors and timeouts encountered by Spring Boot when calling FastAPI.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 8, "x": 0, "y": 73},
        "targets": [
            {"expr": "sum by (operation, error_type) (rate(mformusic_dependency_call_errors_total{dependency=\"fastapi\"}[5m]))", "refId": "A", "legendFormat": "{{operation}}: {{error_type}}"}
        ],
        "fieldConfig": {"defaults": {"unit": "errps", "custom": {"fillOpacity": 10, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    panels.append({
        "id": 34,
        "type": "timeseries",
        "title": "Supabase Storage Latency",
        "description": "Streaming upload and object deletion latency for Supabase Cloud Storage.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 8, "x": 8, "y": 73},
        "targets": [
            {"expr": "mformusic_dependency_call_duration_seconds_sum{dependency=\"supabase\"} / clamp_min(mformusic_dependency_call_duration_seconds_count{dependency=\"supabase\"}, 1)", "refId": "A", "legendFormat": "Avg Latency (s)"}
        ],
        "fieldConfig": {"defaults": {"unit": "s", "custom": {"fillOpacity": 10, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    panels.append({
        "id": 35,
        "type": "timeseries",
        "title": "Supabase Storage Errors",
        "description": "Failed audio uploads or storage deletion errors with Supabase.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 7, "w": 8, "x": 16, "y": 73},
        "targets": [
            {"expr": "sum by (operation, error_type) (rate(mformusic_dependency_call_errors_total{dependency=\"supabase\"}[5m]))", "refId": "A", "legendFormat": "{{operation}}: {{error_type}}"}
        ],
        "fieldConfig": {"defaults": {"unit": "errps", "custom": {"fillOpacity": 10, "showPoints": "never"}, "min": 0}},
        "options": {"tooltip": {"mode": "multi"}}
    })

    dashboard = {
        "uid": "mformusic-service-health",
        "title": "MforMusic - Operational Monitoring",
        "description": "Operational monitoring for MforMusic: Service Health, API Performance, Database & Interaction Writes, Recommendation Reliability, Model Readiness, and Dependencies.",
        "tags": ["mformusic", "operational-monitoring"],
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 2,
        "editable": False,
        "graphTooltip": 1,
        "refresh": "10s",
        "time": {"from": "now-1h", "to": "now"},
        "templating": {"list": []},
        "annotations": {"list": []},
        "links": [
            {
                "type": "dashboards",
                "title": "MforMusic dashboards",
                "tags": ["mformusic"],
                "asDropdown": True,
                "includeVars": False,
                "keepTime": True
            },
            {
                "type": "link",
                "title": "Streamlit: per-user history + SHAP",
                "url": "http://localhost:8501",
                "targetBlank": True,
                "icon": "external link",
                "tooltip": "User-level interaction history and SHAP explanations (not available in Prometheus)"
            }
        ],
        "panels": panels
    }
    return dashboard

if __name__ == "__main__":
    d = build_dashboard()
    with open("monitoring/grafana/dashboards/mformusic-service-health.json", "w") as f:
        json.dump(d, f, indent=2)
    print("Successfully generated mformusic-service-health.json with", len(d["panels"]), "panels!")

