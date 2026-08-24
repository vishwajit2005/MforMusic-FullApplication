# ─────────────────────────────────────────────────────────────────────────────
# MforMusic MLOps FastAPI Service
# Python 3.12 — matches local venv to guarantee wheel compatibility
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

# Build tools for any packages that still need compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Dependency layer (cached until requirements.txt changes) ──────────────────
COPY requirements.txt .

# Install numpy/scipy first with binary-only wheels, then the rest
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "numpy>=1.26" --only-binary :all: && \
    pip install --no-cache-dir scipy --only-binary :all: && \
    pip install --no-cache-dir -r requirements.txt

# ── Application source ────────────────────────────────────────────────────────
COPY app/ app/

# Non-root user
RUN useradd -m -u 1001 mlops
USER mlops

# sentence-transformers model cache — downloaded on first request if not pre-baked
# Mount a volume here in production to persist across restarts
ENV SENTENCE_TRANSFORMERS_HOME=/app/.model_cache
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]
