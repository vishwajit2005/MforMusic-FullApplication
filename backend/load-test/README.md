# MforMusic backend capacity tests

This harness exercises the real Spring Boot application over HTTP and a disposable MySQL database. It does not change production pools, clients, endpoints, or business logic. It does not call the real music wrapper, FastAPI, audio CDN, or object storage.

## Requirements

- Java 21, Maven, Python 3, ripgrep, k6 (the recorded run uses k6 1.0.0).
- An isolated MySQL instance listening on `127.0.0.1:13306`.
- A database named `mformusic_capacity`, with a local test account `capacity` / `capacity-local-only` having access only to that schema. These are disposable test credentials, not production credentials.
- No production environment variables or `.env` files are required. `CapacityApplication` intentionally does not call the production `main()` dotenv loader.

The test configuration checks the datasource URL before Hibernate starts and refuses remote hosts or non-capacity schemas. The test server binds to loopback. The k6 script also refuses non-loopback URLs. Do not weaken these guards to point it at Aiven or production.

## Integration tests

From `backend/`:

```sh
mvn test
```

`BackendFlowsIntegrationTest` starts embedded Tomcat on a random port and uses a real HTTP client, JWT authentication, services, repositories, and MySQL. It covers search/play/like/unlike/recent, cache-miss persistence, telemetry connection-refusal/HTTP-500 isolation, validation, recommendation connection-refusal/HTTP-500 degradation, ranking/count clamping, and a latch-based non-blocking telemetry contract.

The strict async-contract test is expected to expose the current self-invocation defect: `ingestInteraction()` calls `forwardToFastApi()` directly, so the HTTP response cannot complete while the downstream latch is held. Do not suppress this test or relabel it as a pass. A failed FastAPI request and an indefinitely slow FastAPI request are different cases.

The initial execution also found malformed telemetry returns 403 rather than the expected validation 400. The test retains its expected 400 so the behavior remains visible. These tests intentionally do not fix production code.

## Load test

```sh
./load-test/run.sh
```

Optional tool paths and scenario settings:

```sh
K6_BIN=/path/to/k6 MAVEN_BIN=/path/to/mvn JAVA_BIN=/path/to/java \
RUN_NAME=baseline HOLD_SECONDS=40 THINK_SECONDS=4 ./load-test/run.sh

RUN_NAME=slow-upstream SAAVN_DELAY_MS=2000 ./load-test/run.sh
RUN_NAME=cold-catalog MODE=cold ./load-test/run.sh
```

Default workload:

- 15-second warmup; stages of 10, 25, 50, 100, 200, 350, 500 VUs.
- Each stage has a 5-second ramp and 40-second plateau, followed by ramp-down and draining.
- 500 distinct signed users and 2,000 seeded songs; existing fixtures are reused.
- Each loop searches, pauses 0.2–0.5 seconds, plays, emits telemetry, likes on one quarter of iterations, fetches 20 recommendations on one third, then thinks for 3–5 seconds.
- Approximately 2% planned cache-miss plays, spread across users/iterations; `MODE=hot` excludes these, `MODE=cold` uses only misses.
- Controlled wrapper delay 150 ms, FastAPI delay 50 ms, storage operation delay 250 ms. These are assumptions, not measured third-party latency.
- Real JDBC work and the real async upload service are preserved. Only storage I/O is replaced. The wrapper/FastAPI boundary returns realistic JSON through the existing RestTemplate parsing path, with no real outbound sockets.
- 10-second client request timeout. Hikari's production 30-second checkout timeout is unchanged.
- JVM heap explicitly bounded to 512 MiB for reproducibility. This is a test launch setting, not a production configuration change or proof of a hosting-plan limit.

The boundary stub fails closed on unexpected hosts and records attempted blocked requests. It does not emulate an outbound connection pool or TCP/TLS cost. Music playback requests return metadata/URLs; k6 does not download or stream audio.

This is a closed workload: blocked virtual users issue fewer requests. Always report throughput alongside VUs and latency; do not equate virtual users with simultaneous in-flight requests, active streams, or total signed-in users. For subsequent throughput planning, an arrival-rate workload can complement this user-count test.

## Evidence

Each run writes `load-test/results/<RUN_NAME>/`:

- `requests.jsonl`: k6 raw samples tagged by plateau, endpoint, mode, and HTTP status.
- `summary.json`: k6 aggregate results and exact scenario windows.
- `metrics.jsonl`: one-second Hikari active/idle/waiters/timeouts, Tomcat busy/total/max threads and connections, async active/queued/completed tasks, stub request counts, process/system CPU, and heap.
- `threads-*.txt`: thread dumps captured during DB contention.
- `backend.log`, `k6.log`, `results.json`, `table.md`, and `exit-status.txt`.

k6 exit 99 indicates a configured threshold failed; the runner still generates evidence. HTTP 200 with missing recommendations counts as a contract failure in the healthy-stub capacity run so graceful fallback cannot hide overload.

The degradation criterion is endpoint p95 above both 1 second and twice the corresponding 10-VU baseline. Failures are reported separately, including client timeouts and fallback contract failures. Attribute a limit only with resource data and thread/log evidence. A test that passes through 500 VUs establishes no observed breaking point within that workload, not unlimited capacity.

Fixtures accumulate play history, likes, and cache misses across runs. For strict repeats, start a new disposable schema/instance (with the same guarded schema name) and record the MySQL version, machine CPU/RAM, latency assumptions, heap size, dataset counts, and run duration. The local test does not establish Aiven network latency, Aiven service limits, or Render deployment capacity.

## Sources

- [k6 ramping virtual users](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-vus/)
- [k6 closed versus open workloads](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/)
- [Spring proxy self-invocation semantics](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
