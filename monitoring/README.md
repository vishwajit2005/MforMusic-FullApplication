# MforMusic Operational Monitoring (Prometheus + Grafana)

Operational and service-level monitoring for the MforMusic platform:
- **FastAPI MLOps service** (`http://mlops:8000/metrics`)
- **Spring Boot backend** (`http://backend:8080/actuator/prometheus`)
- **Prometheus scraper** (`http://127.0.0.1:9090`)
- **Provisioned Grafana** (`http://127.0.0.1:3000`)

```
FastAPI (mlops:8000)  GET /metrics  (Bearer token)  ◄── Prometheus (127.0.0.1:9090) ◄── Grafana (127.0.0.1:3000)
Spring Boot (backend:8080) /actuator/prometheus     ◄──┘
```

## 1. Start it locally

```bash
# 1) One-time: generate monitoring secrets into the root .env
sh monitoring/scripts/init-monitoring-env.sh

# 2) Start the stack with the monitoring profile
docker compose --profile monitoring up -d --build
```

| Service | Local URL | Authentication | Notes |
|---|---|---|---|
| **Grafana** | [http://127.0.0.1:3000](http://127.0.0.1:3000) | user `admin`, password = `GRAFANA_PASSWORD` in `.env` | Dashboards automatically provisioned |
| **Prometheus** | [http://127.0.0.1:9090](http://127.0.0.1:9090) | No login (loopback only) | Scrapes targets, TSDB & alerts |
| **Prometheus Targets** | [http://127.0.0.1:9090/targets](http://127.0.0.1:9090/targets) | No login | Status of backend & mlops scrape jobs |
| **Streamlit (existing)** | [http://localhost:8501](http://localhost:8501) | Per-user history & SHAP UI | Per-user history & ML explainability |

Dashboards are provisioned in the **MforMusic** folder. The default home dashboard is **Operational Monitoring** (`mformusic-service-health.json`).

---

## 2. Simplified Dashboard Sections

The primary dashboard (`mformusic-service-health.json`) has been simplified to eliminate dead panels and focus strictly on live operational health from the deployed service:

1. **Service Health**
   - **FastAPI (MLOps Engine)**: UP/DOWN status indicator scraped from `/metrics`.
   - **FastAPI Uptime**: Live running duration since process start.
   - **Process Restarts (24h)**: Detects process crashes/restarts over the last 24h.
   - **Prometheus Scrape Status**: Target health for Prometheus self-monitoring.
2. **Model Readiness & Health**
   - **CF (ALS) Model Ready**: Instant indicator (READY / NOT READY) based on `mformusic_model_available{model="collaborative_filtering"}`.
   - **Content (Audio KNN) Ready**: Instant indicator (READY / NOT READY) based on `mformusic_model_available{model="content_based"}`.
   - **CF Active Version**: Displays current artifact version string (e.g., `v_32i_2u_21s`).
   - **Content Active Version**: Displays current audio KNN model version (e.g., `content_knn_v2_1416s`).
   - **Time Since Last Retrain**: Live elapsed seconds since last successful retraining (`Never` if un-retrained).
   - **Retraining Status**: Real-time status indicator (IDLE / TRAINING) when background training runs.
3. **Interactions & Recommendation Activity**
   - **Songs Played per Minute**: Live timeseries of actual playback events per minute (`interaction_type="play"`).
   - **Recommended Songs Listened To**: Live rate of play events where the played song was previously served to that user by the recommendation service.
   - **Songs Served by Model in Last 1h (Individual Tracks)**: Rolling 1-hour count of individual recommended tracks returned to users, partitioned by serving tier (CF, Content-Based, Embeddings, Popular Fallback).
   - **New Interaction Records Written / Minute**: Live ingestion rate of interaction events split by interaction type (`play`, `like`, `unlike`, `skip`, `download`, `playlist_add`).

---

## 3. Metric Groups Reference

### Group 1: Service Availability
- `up{job=~".*mlops.*"}`: 1 if FastAPI is responding to scrapes.
- `process_start_time_seconds`: Process startup timestamp.
- `changes(process_start_time_seconds[24h])`: Process restart detection.

### Group 2: User Activity & Recommendation Telemetry
- `mformusic_telemetry_events_total`: Interaction events ingested by FastAPI (PostgreSQL) by `channel`, `interaction_type`, `result`.
- `mformusic_recommended_plays_total`: Counter incremented whenever an accepted `play` event corresponds to a song previously served to that user as a recommendation.
- `mformusic_recommendation_songs_served_total`: Rolling count of individual songs served across recommendation responses by `mode` and `tier`.
- `http_requests_total`: Handled HTTP requests (FastAPI) by `handler`, `status`, `method` (used as fallback on deployed targets).

### Group 3: Model Serving Health
- `mformusic_model_available`: 1 if model is loaded in memory and serving (`collaborative_filtering`, `content_based`).
- `mformusic_model_info`: Active model artifact version string (`model`, `version`).
- `mformusic_model_last_retrain_success_timestamp_seconds`: Unix timestamp of last completed retrain.
- `mformusic_model_retraining_in_progress`: 1 when background ALS or KNN training is executing.
- `mformusic_recommendation_fallbacks_total`: Fallbacks by `primary_tier`, `served_tier`, and `reason`.
- `mformusic_recommendation_duration_seconds`: Latency histogram of recommendation computation.

### Group 6: Model Serving Health
- `mformusic_model_available`: 1 if model is loaded in memory and serving (`collaborative_filtering`, `content_based`).
- `mformusic_model_info`: Active model artifact version string (`model`, `version`).
- `mformusic_model_last_retrain_success_timestamp_seconds`: Unix timestamp of last successful retrain.
- `mformusic_model_retrains_total`: Training attempts by `model` and `result` (`success`, `failure`, `skipped`).
- `mformusic_model_retrain_duration_seconds`: Runtime duration of completed training runs.

### Group 7: Recommendation Scores
- `mformusic_recommendation_scores_bucket`: Histogram distribution of recommendation scores produced by serving tier (`collaborative_filtering`, `content_based`, `embedding_based`, `popular`).

### Group 8: Dependency Health
- `mformusic_dependency_call_duration_seconds`: Outgoing HTTP latency for dependencies (`dependency="fastapi|external_music_api|supabase|embedding_service"`, `operation`, `status`).
- `mformusic_dependency_call_errors_total`: Errors and timeouts when contacting dependencies.
- `mformusic_kafka_consumer_connected`: 1 if connected to Kafka broker.
- `mformusic_kafka_consumer_errors_total`: Kafka poll or broker connection errors.

---

## 4. Safety & Low-Cardinality Guardrails

- **Zero PII & Unbounded Data**: `user_id`, `song_id`, customer email, raw URLs, and free-text queries are **strictly excluded** from metric labels.
- **Fail-Closed Metrics Protection**: The `/metrics` endpoint requires a Bearer token (`METRICS_TOKEN`) with a minimum length of 16 characters. If unset, it responds with `503 Service Unavailable`.
- **Streamlit vs. Prometheus Separation**: Detailed user-level histories and SHAP feature importance remain solely in the Streamlit application (port 8501). Prometheus and Grafana maintain aggregate operational data only.

## 5. Metrics reference (`mlops/app/core/metrics.py`)

HTTP metrics come from `prometheus-fastapi-instrumentator`: `http_requests_total{handler,method,status}`
and `http_request_duration_seconds{handler,method}` (`handler` is the route template, `status` is `2xx`..`5xx`).

| Metric | Type | Labels |
|---|---|---|
| `mformusic_recommendation_requests_total` | counter | `mode` (for_you, similar), `tier` (content_based, collaborative_filtering, embedding_based, popular, cold_start, error) |
| `mformusic_recommendation_failures_total` | counter | `mode` |
| `mformusic_recommendation_fallbacks_total` | counter | `primary_tier`, `served_tier`, `reason` (no_history, no_positive_history, content_model_unavailable, no_recent_catalog_match, no_content_results, primary_tier_empty) |
| `mformusic_recommendation_duration_seconds` | histogram | `mode`, `tier` |
| `mformusic_model_available` | gauge | `model` (collaborative_filtering, content_based) |
| `mformusic_model_info` | gauge (=1) | `model`, `version` (**only the active version is exported**) |
| `mformusic_model_items` | gauge | `model`, `kind` (interactions, users, songs, tracks) |
| `mformusic_model_retraining_in_progress` | gauge | `model` |
| `mformusic_model_retrains_total` | counter | `model`, `result` (success, failure, skipped) |
| `mformusic_model_retrain_duration_seconds` | histogram | `model` (success/failure runs only) |
| `mformusic_model_last_retrain_success_timestamp_seconds` | gauge | `model` (0 = none since process start) |
| `mformusic_model_artifacts_loaded_timestamp_seconds` | gauge | `model` |
| `mformusic_recommendation_priority_info` | gauge (=1) | `priority` |
| `mformusic_telemetry_events_total` | counter | `channel` (http, kafka), `interaction_type` (play, skip, like, unlike, download, playlist_add, other), `result` (accepted, failed) |
| `mformusic_telemetry_ingest_failures_total` | counter | `channel`, `reason` (validation, database, other) |
| `mformusic_telemetry_ingest_duration_seconds` | histogram | `channel` |
| `mformusic_kafka_consumer_enabled` / `_connected` | gauge | none |
| `mformusic_kafka_consumer_errors_total` | counter | none |
| `mformusic_db_operation_duration_seconds` | histogram | `operation` (select, insert, update, delete, ddl, connect, other) |
| `mformusic_db_errors_total` | counter | `operation`, `error` (operational, integrity, programming, data, other) |
| `mformusic_db_pool_connections` | gauge | `state` (size, checked_out, checked_in, overflow) |

**Cardinality rules:** every label value is checked against a fixed allow-list in code and falls back to `other`.
`user_id`, `song_id`, raw URLs, SQL text and free-text interaction types are never labels. Counters are
process-local and reset when the service restarts (use `increase()`/`rate()`, which handle resets).

## 6. Security notes

* `/metrics` is protected by a bearer token and fails closed (503) when no token is configured.
* Prometheus and Grafana publish ports on `127.0.0.1` only. Prometheus has no authentication and
  runs with `--web.enable-lifecycle`, so do not expose port 9090 beyond your machine.
* The scrape token is written to an in-memory `tmpfs` inside the Prometheus container at start-up; it is not stored in
  `prometheus.yml` or on a Docker volume.
* Cloud (Render): the deployment wrapper (`app/deployment/auth.py`) requires `X-MforMusic-Key` on every path except
  `/health` and `/metrics`. `/metrics` skips the shared key only because it enforces its own fail-closed bearer token
  (`METRICS_TOKEN`). That token grants read-only metrics and does not unlock any API route (covered by tests). See section 9.

## 7. Known limits and follow-ups

* **Telemetry "forwarding":** FastAPI can only observe the receiving side. Spring Boot's own forwarding success or
  failure (to Kafka or HTTP) is not exported by any custom metric today; add Micrometer counters in
  `TelemetryService` / `TelemetryEventProducer` if you need it. The dashboard compares Spring's endpoint rate with FastAPI's received rate.
* Single Uvicorn worker is assumed (counters live in process memory), as in the current Dockerfile.
* Alertmanager is not part of Compose; alert rules in `alert_rules.yml` evaluate and show in Prometheus' Alerts page only.
* No alert rules were added for the new ML metrics.

## 8. Tests

```bash
cd mlops
python -m pytest tests/test_prometheus_metrics.py -q
```

## 9. Monitor the deployed (Render) app from your machine

Prometheus and Grafana run **locally** in Docker, but scrape the **deployed** API at
`https://mformusic-mlops.onrender.com/metrics`. Nothing else from the local stack runs.

```
Render: mformusic-mlops  GET /metrics (Bearer METRICS_TOKEN)  ◄── Prometheus (127.0.0.1:9090) ◄── Grafana (127.0.0.1:3000)
```

Files: `docker-compose.cloud-monitoring.yml`, `monitoring/prometheus.cloud.yml` (Grafana provisioning and dashboards are shared with the local stack).

### Setup (once)

1. `sh monitoring/scripts/init-monitoring-env.sh` creates `CLOUD_METRICS_TOKEN` and `GRAFANA_PASSWORD` in the git-ignored root `.env`.
2. In the Render dashboard open **mformusic-mlops → Environment** and add `METRICS_TOKEN` with the **same value** as
   `CLOUD_METRICS_TOKEN` (show it with `grep '^CLOUD_METRICS_TOKEN=' .env`). It needs at least 16 characters.
3. Deploy this version of the code (`/metrics` and the auth change exist only after it is deployed). Setting the env var in
   the dashboard first is safe: older code simply ignores it.
4. Start the stack: `docker compose -f docker-compose.cloud-monitoring.yml up -d`.
   It refuses to start (with a clear message) if `CLOUD_METRICS_TOKEN` or `GRAFANA_PASSWORD` is missing.

### Verify

```bash
set -a; . ./.env; set +a
U=https://mformusic-mlops.onrender.com/metrics
curl -s -o /dev/null -w "%{http_code}\n" $U                                                  # 401 (no token)
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $CLOUD_METRICS_TOKEN" $U  # 200
```

Then http://127.0.0.1:9090/targets shows `mformusic-mlops` **UP** with `environment="render"`, and Grafana
(http://127.0.0.1:3000, user `admin`) shows the MforMusic dashboards.

| Symptom | Cause |
|---|---|
| `curl` returns 404 | The old code (without `/metrics`) is still deployed. Wait for the Render deploy to finish. |
| 503 | `METRICS_TOKEN` is not set on the Render service, or shorter than 16 characters. |
| 401 with the token | Token differs from `CLOUD_METRICS_TOKEN` in `.env`. After editing `.env`, run `docker compose -f docker-compose.cloud-monitoring.yml up -d --force-recreate prometheus`. |
| Timeout / target DOWN once | The free service was asleep; the first request can take up to about a minute. The next scrape recovers. |
| Panels show "No data" | No recommendation or telemetry traffic since the last Render restart (counters start at zero), or the target is DOWN. |

### Things to know

* **Cost of scraping:** every scrape is inbound traffic, so the free Render service never sleeps while Prometheus is running, and it
  uses your monthly free instance hours. The scrape interval is 60 s. Stop the stack when you are not using it:
  `docker compose -f docker-compose.cloud-monitoring.yml down` (add `-v` to also delete the stored history).
* **History lives on your machine** (a Docker volume) and only grows while the stack is running.
* **Counters reset** whenever Render restarts or redeploys the service; `rate()` and `increase()` handle that.
* **Kafka** is disabled on Render, so the Kafka panels show "HTTP only".
* **Spring Boot backend is not scraped** (the block in `prometheus.cloud.yml` is commented out): confirm
  `/actuator/prometheus` on Render is protected first. The "Spring Boot" tile and the Spring telemetry panels show `n/a`.
* **Ports:** this stack and the local `monitoring` profile both use 9090 and 3000; run only one.
* The **Streamlit** link in each dashboard's top bar points to `localhost:8501` (local stack). For the deployed per-user/SHAP view use your
  `mformusic-monitor` service URL on Render.
