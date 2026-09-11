#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${K6_BIN:=k6}"
: "${MAVEN_BIN:=mvn}"
: "${JAVA_BIN:=java}"
: "${RUN_NAME:=baseline}"
OUT="$(pwd)/load-test/results/$RUN_NAME"
mkdir -p "$OUT"
# Fixtures guard enforces loopback MySQL and the disposable schema prefix.
"$MAVEN_BIN" -q test-compile dependency:build-classpath -Dmdep.includeScope=test -Dmdep.outputFile=target/test-classpath.txt
CP="target/test-classes:target/classes:$(cat target/test-classpath.txt)"
"$JAVA_BIN" -Xms256m -Xmx512m -Dcapacity.metrics="$OUT/metrics.jsonl" -cp "$CP" \
  com.mformusic.backend.capacity.CapacityApplication \
  --capacity.tokens-file="$OUT/tokens.json" \
  --capacity.saavn-delay-ms="${SAAVN_DELAY_MS:-150}" \
  --capacity.fastapi-delay-ms="${FASTAPI_DELAY_MS:-50}" \
  --capacity.upload-delay-ms="${UPLOAD_DELAY_MS:-250}" > "$OUT/backend.log" 2>&1 &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true; wait "$BACKEND_PID" 2>/dev/null || true' EXIT
ready=false
for attempt in $(seq 1 120); do
  if rg -q CAPACITY_METRICS_READY "$OUT/backend.log"; then ready=true; break; fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then tail -50 "$OUT/backend.log"; exit 1; fi
  sleep 1
done
if [ "$ready" != true ]; then tail -50 "$OUT/backend.log"; exit 1; fi
set +e
TOKENS_FILE="$OUT/tokens.json" SUMMARY_FILE="$OUT/summary.json" "$K6_BIN" run \
  --out "json=$OUT/requests.jsonl" load-test/capacity.js > "$OUT/k6.log" 2>&1
STATUS=$?
set -e
# Keep violations observable; k6 exit 99 means configured thresholds were exceeded.
python3 load-test/report.py "$OUT/requests.jsonl" "$OUT/metrics.jsonl" --output "$OUT/results.json" | tee "$OUT/table.md"
printf 'k6 exit code: %s\n' "$STATUS" | tee "$OUT/exit-status.txt"
exit "$STATUS"
