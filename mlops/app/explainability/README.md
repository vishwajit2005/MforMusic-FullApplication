# MforMusic — Recommendation Explainability

This module provides **explainability** for the MforMusic recommendation engine.
It answers: *"Why was this song recommended to this user?"*

---

## Architecture

```
MySQL + PostgreSQL
       ↓
 build_dataset.py   ← Offline, run periodically
       ↓
 explainability_training_data.parquet
       ↓
 train_surrogate.py  ← Train XGBoost surrogate
       ↓
 surrogate_model.joblib + feature_list.joblib
       ↓
 shap_engine.py      ← Compute SHAP explanations
       ↓
 shap_explainer.joblib + global_importance.json + feature_metadata.json
       ↓
 api.py              ← FastAPI endpoints (loaded once at startup)
       ↓
 dashboard/app.py    ← Streamlit UI
```

---

## ⚠️ Known Data Limitations

### tier_used and content_similarity_score

**`tier_used` and `content_similarity_score` are only reliably known for
interactions going forward, once recommendation-serving events begin being
logged (see Future Improvement below). All historical training rows use
`"unknown"` / `0` for these fields respectively, which the surrogate model
and SHAP explanations should be interpreted as reflecting.**

#### Why

The system logs user interactions (play, skip, like, etc.) but does **not**
log *"this song was shown as a recommendation by tier X with seed song Y"*.
Because that recommendation-serving event was never recorded:

- **`tier_used`** — we cannot know which tier (CF / content-based / popular)
  served a given historical interaction. A user's current interaction count
  (used by the live system to pick a tier) is *not* the same as their count
  at the time that historical interaction happened. Retroactively applying
  today's tier-selection logic would produce historically inaccurate values
  and would create a quietly fabricated column in what is supposed to be an
  explainability system.

  **Fix applied:** all historical rows use `tier_used = "unknown"` (a fourth
  one-hot category alongside CF / content-based / popular). The surrogate
  model learns that these rows carry no tier signal, rather than defaulting
  them into a known tier.

- **`content_similarity_score`** — without knowing the tier, we cannot know
  the seed song, so no similarity score can be computed for historical rows.

  **Fix applied:** `content_similarity_score = 0.0` for all historical rows,
  consistent with how the original spec already handles non-content-based
  recommendations — extended to *"we don't know which tier it came from"*.

#### Coverage gap: genre_language_match

`genre_language_match` depends on a song having a row in
`song_audio_features` (the content-model candidate pool). Songs outside
that pool have no language data. **For these songs, `genre_language_match`
defaults to `0` (no match)** rather than being left null. This is a known
limitation — it will resolve naturally as more songs are added to the
content-model pool.

---

## Quickstart

### 1. Install dependencies

```bash
cd mlops/
pip install -r requirements.txt
```

### 2. Set environment variables

Make sure your `.env` has:
```
DATABASE_URL=postgresql://...    # PostgreSQL (FastAPI DB)
MYSQL_URL=mysql+pymysql://...    # MySQL (Spring Boot DB)
```

### 3. Build the dataset

```bash
cd mlops/
python -m app.explainability.build_dataset
```

Output: `app/explainability/dataset/explainability_training_data.parquet`

Each row = one interaction event. Aggregate features (skip_count,
user_play_count, completion_rate) are computed from **prior** interactions
only (i.e., those with earlier timestamps) to prevent the current event
from inflating its own feature counts.

### 4. Train the surrogate model

```bash
python -m app.explainability.train_surrogate
```

Output: `app/explainability/artifacts/surrogate_model.joblib`

Reports **R²** and **MAE** on the held-out 20% test set.
If R² < 0.3, the feature list may be missing something important.

> **Note on current R²:** Because `tier_used` is `"unknown"` for all
> historical rows and `content_similarity_score` is always `0`, the model
> cannot use these two dimensions at all in its initial training. The R²
> will reflect what is learnable from the remaining 9 features
> (play history, likes, skip rate, completion, language/decade match,
> popularity, recency). This is honest. R² will improve once
> recommendation-serving events are logged (see Future Improvement).

### 5. Compute SHAP explanations

```bash
python -m app.explainability.shap_engine
```

Output:
- `artifacts/shap_explainer.joblib` — pickled SHAP TreeExplainer
- `artifacts/global_importance.json` — mean |SHAP| per feature
- `artifacts/feature_metadata.json` — human-readable labels for UI

### 6. Start the FastAPI service

```bash
uvicorn app.main:app --reload --port 8000
```

New endpoints:
- `GET /api/v1/explainability/global-importance`
- `GET /api/v1/explainability/factors`
- `GET /api/v1/explainability/recommendation/{user_id}/{song_id}`
- `GET /api/v1/explainability/status`

### 7. Launch the Streamlit dashboard

```bash
streamlit run app/explainability/dashboard/app.py
```

---

## Feature List (Single Source of Truth)

| Feature | Description | Source | Notes |
|---|---|---|---|
| `likes_count` | Total likes across all users | MySQL `user_liked_songs` | |
| `user_play_count` | Times this user played this song (prior interactions only) | MySQL `user_interactions` | Leakage-guarded |
| `skip_count` | Times this user skipped this song (prior interactions only) | MySQL `user_interactions` | Leakage-guarded |
| `completion_rate` | Avg listen fraction (prior interactions only) | MySQL `user_interactions` | Leakage-guarded |
| `genre_language_match` | 1 if song language = user's fav; 0 if no audio features for song | PG `song_audio_features` | Coverage gap for songs outside content pool |
| `decade_match` | 1 if song decade = user's fav | PG `song_audio_features` | |
| `content_similarity_score` | **Always 0.0 for historical data** | N/A (not logged) | See limitation note above |
| `popularity_score` | Log-normalized global play count | MySQL `songs` | |
| `recency_days` | Days since user's last PRIOR interaction with this song | MySQL `user_interactions` | |
| `tier_used` | **Always "unknown" for historical data** (one-hot encoded) | N/A (not logged) | See limitation note above |

---

## Leakage Guard

The dataset is built one row per **interaction event** (not per user-song
pair). For each row, the aggregate features (`skip_count`, `user_play_count`,
`completion_rate`) are computed from all interactions for that (user, song)
pair with a timestamp **strictly earlier** than the current row's
`device_timestamp`.

This prevents a skip event's own skip from inflating `skip_count`, or a
play event's completion rate from being included in its own
`completion_rate` average — both of which would be mild forms of target
leakage since the target (`interaction_score`) is derived from the same
event.

---

## Regeneration Schedule

These are **offline jobs** — they do NOT need to run per-request.

| Job | Recommended frequency |
|---|---|
| `build_dataset.py` | Weekly or after major data growth |
| `train_surrogate.py` | After rebuilding dataset |
| `shap_engine.py` | After retraining surrogate |

After regenerating artifacts, **restart the FastAPI service** so the new
artifacts are loaded.

---

## Future Improvement (Not In Scope for Current Task)

> ⚠️ **Do NOT implement this as part of the current task.** This touches
> the live recommendation-serving path, which is explicitly read-only/
> additive-only for this feature. This note exists so a future contributor
> understands the limitation and how to resolve it.

The live recommendation-serving code path (in `recommendation_service.py`)
could log a **lightweight event** at the moment a recommendation batch is
actually served:

```json
{
  "user_id": "42",
  "song_id": "jiosaavn_abc123",
  "tier": "collaborative_filtering",
  "model_version": "cf-v7",
  "served_at_ms": 1720000000000,

  // content-based tier only:
  "seed_song_id": "jiosaavn_xyz456",
  "similarity_score": 0.82
}
```

Once this log exists (e.g., written to a new `recommendation_serving_log`
table or a Kafka topic), `build_dataset.py` can join it against
`user_interactions` by `(user_id, song_id, timestamp)` to populate real
`tier_used` and `content_similarity_score` values for future training rows.

This would make `tier_used` and `content_similarity_score` genuinely
informative dimensions in the surrogate model, improving SHAP explanation
quality for those features. Historical rows would remain `"unknown"` / `0`
and be progressively diluted as new logged rows accumulate.

---

## Notes

- **Purely additive** — no existing endpoints, models, or tables are modified.
- All four modules (`build_dataset.py`, `train_surrogate.py`, `shap_engine.py`,
  `api.py`) reference the same `FEATURES` list — never modify the list in
  just one place.
