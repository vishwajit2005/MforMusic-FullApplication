#!/usr/bin/env sh
# Generates the two monitoring secrets and appends them to the repo-root .env (which is git-ignored).
# Existing non-empty values are never overwritten.
#
# Usage (from anywhere):  sh monitoring/scripts/init-monitoring-env.sh
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="$ROOT/.env"

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl not found. Create the values yourself, e.g. METRICS_TOKEN=<32+ random chars> in $ENV_FILE" >&2
  exit 1
fi

touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

add_if_missing() {
  key="$1"; bytes="$2"
  if grep -Eq "^${key}=.+" "$ENV_FILE"; then
    echo "$key is already set in .env - left unchanged"
  else
    printf '%s=%s\n' "$key" "$(openssl rand -hex "$bytes")" >> "$ENV_FILE"
    echo "$key generated and added to .env"
  fi
}

add_if_missing METRICS_TOKEN 32        # protects GET /metrics on the LOCAL FastAPI container
add_if_missing CLOUD_METRICS_TOKEN 32  # must equal METRICS_TOKEN on the mformusic-mlops Render service
add_if_missing GRAFANA_PASSWORD 16     # Grafana admin password (user: admin)

echo
echo "Monitor the DEPLOYED app (Render):"
echo "  1) In the Render dashboard, open mformusic-mlops -> Environment and add METRICS_TOKEN with the value of"
echo "     CLOUD_METRICS_TOKEN from $ENV_FILE  (show it with: grep '^CLOUD_METRICS_TOKEN=' .env)"
echo "  2) docker compose -f docker-compose.cloud-monitoring.yml up -d"
echo
echo "Monitor the LOCAL stack instead: docker compose --profile monitoring up -d --build"
echo "Grafana login: user 'admin', password = GRAFANA_PASSWORD from $ENV_FILE"
