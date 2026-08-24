# MforMusic MLOps — Recommendation Engine

FastAPI microservice implementing real-time collaborative filtering (ALS) for the MforMusic platform.

## Architecture

```
Spring Boot Backend
    │  POST /api/v1/interactions/ingest  (telemetry forwarded from Android)
    │  GET  /api/v1/recommendations/{userId}  (proxied to Android)
    ▼
FastAPI MLOps Service  (this service)
    ├── PostgreSQL + pgvector
    ├── ALS Collaborative Filter (implicit library)
    └── Hourly model retraining (APScheduler)
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/interactions/ingest` | Receive telemetry events from Spring Boot |
| `GET` | `/api/v1/recommendations/{userId}` | Personalized recommendations |
| `GET` | `/api/v1/recommendations/model/status` | CF model training status |
| `POST` | `/api/v1/recommendations/model/retrain` | Manual retrain trigger |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger UI |

## Local Development

### 1. Start PostgreSQL with pgvector
```bash
docker run -d \
  --name mlops-pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=mlops_db \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

### 2. Create virtual environment

> **Requires Python 3.12.** Python 3.14 is too new — `pydantic-core` and `psycopg2-binary`
> don't have wheels for it yet. Use the Homebrew-installed 3.12:
> ```bash
> /opt/homebrew/bin/python3.12 --version   # should print Python 3.12.x
> ```

```bash
cd mlops/
/opt/homebrew/bin/python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env — set DATABASE_URL if using non-default PostgreSQL
```

### 4. Run the service
```bash
uvicorn app.main:app --reload --port 8000
```

Open Swagger UI: http://localhost:8000/docs

### 5. Test ingestion
```bash
curl -X POST http://localhost:8000/api/v1/interactions/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "42",
    "song_id": "jiosaavn_track_xyz",
    "interaction_type": "play",
    "play_duration_sec": 210,
    "completion_rate": 0.92,
    "session_id": "sess_test_001",
    "device_timestamp": 1755600000000
  }'
```

### 6. Get recommendations (after ≥ 3 interactions for a user)
```bash
curl http://localhost:8000/api/v1/recommendations/42?n=10
```

## Interaction Scoring (CF Weight Matrix)

| Type | Score | Notes |
|---|---|---|
| `play` | `completion_rate × 3.0` (min 0.1) | Full listen = 3.0, partial = scaled |
| `like` | 4.0 | Explicit strong positive |
| `download` | 3.5 | High intent (offline access) |
| `playlist_add` | 3.0 | Intentional curation |
| `skip` | 0.01 | Negative signal (clamped for ALS) |
| `unlike` | 0.01 | Negative signal (clamped for ALS) |

## Cold Start Strategy

- Users with **< 3 interactions** get globally popular songs (by weighted interaction score)
- Once a user crosses the threshold and the model retrains, they get CF recommendations
- Response includes `"source": "collaborative_filtering" | "popular"` so clients know which strategy was used

## Model Retraining

Retraining is triggered by **two mechanisms**:
1. **Threshold**: Every 50 ingested interactions (configurable via `RETRAIN_EVERY_N_INTERACTIONS`)
2. **Schedule**: Every hour (configurable via `RETRAIN_INTERVAL_SECONDS`)

Retraining runs in a background daemon thread — **zero downtime** via atomic model state swap under `RLock`.

## Production Deployment (Render.com)

1. Create a **PostgreSQL** instance on Render (supports pgvector)
2. Set environment variables:
   ```
   DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
   ```
3. Deploy as a Web Service with:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`

> **Important:** Use `--workers 1` — the ALS model is an in-memory singleton. Multiple workers each train their own model, which wastes RAM. For horizontal scaling, externalize the model to Redis or a model registry.

## Enabling Spring Boot Integration

Set in `backend/src/main/resources/application.properties`:
```properties
mlops.fastapi.enabled=true
mlops.fastapi.url=https://your-mlops-service.onrender.com
```

Or via environment variables:
```bash
MLOPS_FASTAPI_ENABLED=true
MLOPS_FASTAPI_URL=https://your-mlops-service.onrender.com
```
