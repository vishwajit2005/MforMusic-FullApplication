# MforMusic free cloud deployment

Aiven PostgreSQL stores recommendation interactions and pgvector embeddings. Existing Aiven MySQL remains the application database. Supabase remains the existing audio storage provider.

Three free Render services use the current monorepo:
- mformusic-embeddings: existing MiniLM encoder, isolated for its memory budget.
- mformusic-mlops: existing recommendation, content, telemetry and SHAP endpoints. Its deployment entry point injects a remote encoder without changing model calculations.
- mformusic-monitor: existing Streamlit dashboard behind a password gate.

Each API process has one worker. Protected endpoints require X-MforMusic-Key. Only /health is public. Backend AppConfig adds the header only for requests to the configured MLOps origin and path. The dashboard adds it only for its configured service URL. Secrets belong in the hosting provider environment, never Git. Local deployment secrets are in ignored mlops/.env.cloud (mode0600).

cloud-start.py resolves the bundled Aiven CA location and requires certificate and hostname verification for both databases. cloud-build.sh installs CPU-only PyTorch and XGBoost; the embeddings role downloads the existing MiniLM model during build. Saved content and SHAP artifacts ship with the repository; their manifest records original checksums.

## Limits

This is a free demonstration deployment, not an always-on capacity guarantee. Render free services share the workspace hour allowance and can sleep; a request spanning sleeping services may exceed the current client timeout. No keep-awake traffic is configured. Aiven free PostgreSQL has 20 connection slots and may power off after inactivity. Do not run multiple API workers or simultaneous local/cloud copies against it without budgeting connections.

Content artifacts written by automatic retraining use ephemeral service storage. Restart restores the committed baseline. CF reconstructs from persistent PostgreSQL interactions. Durable storage for newly trained content artifacts is not implemented in this deployment pass. Audio feature extraction and retraining peak memory are not yet validated under 512 MiB; ordinary inference checks do not prove those workloads.

The existing backend service must use the monorepo's backend directory as Docker root/context, the same Aiven MySQL credentials, MLOPS_FASTAPI_ENABLED=true, MLOPS_FASTAPI_URL pointing at the deployed API, MLOPS_API_KEY matching the model services, and KAFKA_TELEMETRY_ENABLED=false for its existing direct HTTP fallback.

render.yaml records the intended free service configuration. Existing services created through the Render API should not be duplicated by applying a second Blueprint.
