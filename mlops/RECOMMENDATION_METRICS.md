# Recommendation serving metrics

`GET /api/v1/recommendations/metrics/distribution`

The endpoint reports the last **100 completed For You recommendation-handler requests** in this FastAPI worker. It includes recommendation fetches from the Android backend, dashboard and direct API callers. It is request-weighted, not a percentage of unique users. Reading the metrics endpoint does not add an observation. The separate Now Playing `/similar` query is excluded so it cannot distort the For You fallback rate.

The cloud deployment requires the existing `X-MforMusic-Key` header. No user IDs, song IDs or credentials are stored in the counter. One short structured log entry also identifies the serving source, configured priority and content fallback reason for successful handler calls.

## Response

- `observed_requests`: actual sample size, from 0 to 100. An empty window has zero counts/percentages, not evidence of adequate coverage.
- `distribution`: counts and percentages for `content_based`, `collaborative_filtering`, `popular`, `cold_start`, and `error`. The denominator is all observed requests. Rounding can make the percentages sum slightly differently from 100.
- `cold_start`: the existing empty-popularity response; kept separate instead of being mislabelled Popular.
- `error`: an exception handled by the recommendation handler. Authentication failures, request validation rejections, dependency failures before the handler and downstream Spring/app failures are not included.
- `fallback_reasons`: counts among Popular and cold-start responses only. These explain why content recommendations were unavailable, not why CF was unavailable.
- `priority_counts`: counts under `content_first` and/or `cf_first`, useful when interpreting the serving distribution.
- `oldest_request_at`, `newest_request_at`, `tracking_started_at`: UTC timestamps identifying the window and collection lifetime.
- `scope=process_local`, `resets_on_restart=true`: bounded in-memory storage. Each worker has its own window. The current cloud launcher uses one API worker. Multiple workers/instances would require shared storage for a combined distribution; no such infrastructure is added here.

Illustrative example only: after 70 content-based, 5 CF and 25 Popular outcomes, the endpoint reports 70%, 5%, and 25%, respectively. This distribution is verified by a test; it is not claimed as real app traffic.

## Reading the numbers

A high Popular share is a fallback signal, **not proof by itself that the catalogue is too small**. Interpret it alongside the fallback reasons:

| Reason | Meaning |
|---|---|
| `no_recent_catalog_match` | None of the latest ten positive events matches the current catalogue. Sustained high counts make catalogue coverage a priority to investigate. |
| `no_history` | No recorded interactions for this account; expanding the catalogue alone will not solve that. |
| `no_positive_history` | No eligible positive events; skips/unlikes never seed a profile. |
| `content_model_unavailable` | Content artifacts are not ready; investigate loading/availability. |
| `no_content_results` | At least one seed matches, but the query returned nothing. Candidates may be exhausted after exclusions, the vector may be unusable, or the query may have failed; inspect service logs. |
| `unknown` | No diagnostic reason was supplied. |

Under content-first serving, consistently high content share and low Popular share across representative real traffic suggest expansion is not the immediate priority. Low Popular alone does not prove adequate coverage: CF can compensate for missing content coverage, and serving a nonempty result does not prove recommendation quality. A few repeated dashboard requests or one active user can dominate a small window.

Look at multiple recent windows over real usage to assess persistence. This counter does not retain historical windows or survive restarts; structured service logs can supplement it. A worker restart starts a fresh sample.

## Scope

No dataset expansion, retraining changes, ranking changes, production deployment or dashboard redesign is part of Phase 3. Phase 1 multi-seed profiles and Phase 2 configurable priority remain local. The recommendation response schema is unchanged; diagnostics are collected separately and do not leak into that response.
