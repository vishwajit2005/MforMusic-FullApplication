# Similar Songs — Now Playing query

`GET /api/v1/recommendations/similar`

Required query parameters: `user_id`, `current_song_id`.
Optional: repeated `context_song_ids` parameters (zero to four, newest prior play first); `n` (1–50, default 20).

```text
/api/v1/recommendations/similar?user_id=1&current_song_id=gyZBnBSJ&context_song_ids=aRZbUYD7&context_song_ids=YiVML4Zo&n=10
```

The caller supplies song IDs only. One read of the user's stored interaction history, ordered by created_at descending and then id descending, supplies exclusions, context quality and recent rejections. There is no additional database query or model load for the rejection penalty.

## Context quality

Current song has fixed raw weight **70**. Context recency weights are **12, 8, 6, 4**, multiplied by quality from each song's latest positive event:

| Event | Quality multiplier |
|---|---:|
| like / playlist_add | 1.5 |
| download | 1.4 |
| play with valid completion | 0.5 + completion clamped to [0,1] |
| play with missing, null or invalid completion | 0.8 |
| No positive event, including no history record at all | 0.8 |

Skip/unlike/unknown events never supply positive quality. A context song supplied by the caller with only negative history still receives the specified default 0.8. A later skip does not replace an earlier positive event for quality lookup; it can independently contribute to rejection avoidance.

Unknown catalogue tracks are removed before normalization. Remaining weights sum to one before the shared vector query. The current song's raw weight is never multiplied by quality. With all four contexts at maximum quality, context weight sums to 45 and the current contribution is 70/115, still dominant. With no positive context records, the context sum is 24 and current contributes 70/94.

Unknown current song uses available context alone. All unknown inputs return an empty list. The full historical exclusion set remains in force, along with every current/context song ID. Repeated context plays retain their event positions.

## Soft rejection re-ranking

Only Similar Songs applies this step, after the existing NearestNeighbors query has returned its candidate list. The model, cosine metric, neighbour count, candidate membership and exclusions are unchanged.

Select the newest five matching history events BEFORE catalogue filtering:

- unlike, regardless of completion;
- skip with completion below 0.2, or missing/null completion.

Exactly 0.2 is not a strong skip. Treating missing skip completion as negative is an explicit product decision, not proof of short playback.

Average the available reject vectors without weights. If none exist or the centroid is zero/nonfinite, retain original results. Otherwise, on a copy of those results:

```text
REJECT_SIMILARITY_THRESHOLD = 0.75
REJECT_PENALTY = 0.30
penalty_flag = 1 if cosine(candidate, reject_centroid) > 0.75 else 0
adjusted_score = original_score * (1 - REJECT_PENALTY * penalty_flag)
```

Sort descending by adjusted score, retaining original order for ties; assign ranks starting at one. The constants are module-level, not environment settings. Any exception during rejection selection, centroid construction or re-ranking logs a warning and returns the complete original result list unchanged, with no partial penalties. The work is synchronous and small, under the same model lock as retrieval to avoid mixing artifact versions.

## API and scope

Response: user_id, current_song_id, recommendations (song_id/score/rank), model_version, total, source=content_based. On an empty result, source identifies query mode rather than asserting that recommendations exist.

No CF or Popular fallback. Unknown/unready/unusable/exhausted content queries return HTTP 200 with an empty recommendation list. Database/request processing errors still return HTTP 500; invalid inputs return HTTP 422.

The static `/similar` route precedes `/{user_id}`. Cloud access uses existing `X-MforMusic-Key` authentication. Android should call through its authenticated Spring backend; do not embed the shared service key in Android. The Android button and Spring proxy are not implemented by this endpoint work.

For You's latest-ten-positive-event weighting, shared neighbour-query helper, serving order, CF training, popularity and semantic search are unchanged. Similar Songs remains excluded from the For You distribution counter.

## Verification

**66 tests pass: the existing 50 plus 16 new test methods**, with parameterized cases inside several methods.

Existing assertions updated:
- Current-dominance and short-versus-broad-profile tests now expect `[24/94, 70/94]` when no positive context records exist, instead of `[0.3, 0.7]`.
- Endpoint history fixtures now supply ordered events with type/completion rather than ID-only rows. Exclusion assertions remain intact.
- Context-only expectations and For You expectations remain unchanged.

New tests cover all quality multipliers, valid zero completion, invalid/missing completion, latest-positive selection, absent and negative-only histories, normalized weights after catalogue filtering, unchanged neighbour settings, one read-only history lookup, strict cosine and skip boundaries, unweighted centroids, five-event limits, stable ties, no original-result mutation, zero/invalid/absent reject vectors, and exception fallback with warnings.

Structural checks confirm For You, ingestion and the shared query helper are unchanged. Saved artifact hashes and CF training/scheduler files are unchanged. A smoke check on the actual 1,411-track model returns ten ordered, excluded Similar Songs results with quality and rejection inputs; the earlier controlled For You result remains exactly equal.

All changes remain local. No dataset expansion, training, push or deployment.
