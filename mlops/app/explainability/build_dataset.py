"""
build_dataset.py — Phase 1 of the MforMusic Explainability Pipeline
=====================================================================
Pulls data from both MySQL (Spring Boot DB) and PostgreSQL (FastAPI DB),
assembles a feature matrix for training the XGBoost surrogate model,
and saves it as a Parquet file.

Run this script periodically (e.g., weekly) to refresh the training data.
It does NOT need to run per-request.

Usage:
    cd mlops/
    python -m app.explainability.build_dataset

Environment variables required (in addition to the standard .env):
    DATABASE_URL         — PostgreSQL connection (already in .env)
    MYSQL_URL            — MySQL connection string, e.g.:
                           mysql+pymysql://user:pass@host:3306/mformusic_db

─────────────────────────────────────────────────────────────────────────────
DATA HONESTY NOTE
─────────────────────────────────────────────────────────────────────────────
Two features in this pipeline — tier_used and content_similarity_score —
are only reliably known for interactions going forward, once
recommendation-serving events begin being logged (see "Future Improvement"
in README.md). All historical training rows produced by this script use
"unknown" / 0 respectively for these fields, which the surrogate model and
SHAP explanations should be interpreted as reflecting.

This is intentional. The alternative — retroactively guessing which tier
served a historical interaction using today's tier-selection logic — would
produce historically inaccurate values and undermine the surrogate's
validity without being visible anywhere downstream.
─────────────────────────────────────────────────────────────────────────────

LEAKAGE GUARD
─────────────────────────────────────────────────────────────────────────────
For each training row (one row per INTERACTION EVENT, not per user-song pair),
the aggregate features (skip_count, user_play_count, completion_rate) are
computed from all OTHER prior interactions for that (user, song) — i.e., all
interactions with a timestamp strictly earlier than the current row's
device_timestamp. This prevents a row's own interaction type from being
counted in its own features (mild target leakage).
─────────────────────────────────────────────────────────────────────────────
"""

import logging
import math
import os
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Output path ───────────────────────────────────────────────────────────────
DATASET_DIR = Path(__file__).parent / "dataset"
DATASET_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = DATASET_DIR / "explainability_training_data.parquet"

# ── Feature list (SINGLE SOURCE OF TRUTH — keep in sync with train_surrogate.py,
#    shap_engine.py, and api.py) ───────────────────────────────────────────────
CATEGORICAL_FEATURES = ["tier_used"]
NUMERIC_FEATURES = [
    "likes_count",
    "user_play_count",
    "skip_count",
    "completion_rate",
    "genre_language_match",
    "decade_match",
    "content_similarity_score",
    "popularity_score",
    "recency_days",
]
TARGET_COL = "interaction_score"


# ── Interaction scoring formula (mirrors CF engine) ───────────────────────────
SCORE_MAP = {
    "play": 1.0,
    "like": 3.0,
    "download": 2.0,
    "playlist_add": 2.0,
    "skip": -0.5,
    "unlike": -1.0,
}


def _score(interaction_type: str, completion_rate: float) -> float:
    base = SCORE_MAP.get((interaction_type or "").lower(), 0.5)
    # Completion-rate bonus: +0 at 0% → +1.0 at 100%
    bonus = completion_rate if completion_rate is not None else 0.0
    return base + bonus


def _safe_log_norm(series: pd.Series) -> pd.Series:
    """Log-normalize a series (handles zeros gracefully)."""
    log_vals = series.apply(lambda x: math.log1p(max(x, 0)))
    max_val = log_vals.max()
    return log_vals / max_val if max_val > 0 else log_vals


def _get_mysql_engine():
    mysql_url = os.environ.get("MYSQL_URL")
    if not mysql_url:
        # Try loading from .env manually (dotenv not always available)
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("MYSQL_URL="):
                    mysql_url = line.split("=", 1)[1].strip()
                    break
    if not mysql_url:
        raise EnvironmentError(
            "MYSQL_URL environment variable not set.\n"
            "Example: MYSQL_URL=mysql+pymysql://root:pass@localhost:3306/mformusic_db"
        )
    return create_engine(mysql_url, pool_pre_ping=True)


def _get_pg_engine():
    from app.core.config import get_settings
    settings = get_settings()
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True)


# ── MySQL queries ─────────────────────────────────────────────────────────────

def _fetch_mysql_interactions(mysql_engine) -> pd.DataFrame:
    """Fetch all interactions from MySQL user_interactions table."""
    logger.info("[MySQL] Fetching user_interactions...")
    query = text("""
        SELECT
            user_id,
            song_id,
            interaction_type,
            play_duration_sec,
            completion_rate,
            device_timestamp
        FROM user_interactions
        ORDER BY device_timestamp ASC
    """)
    with mysql_engine.connect() as conn:
        rows = conn.execute(query).mappings().all()
        df = pd.DataFrame(rows)
        if df.empty:
            df = pd.DataFrame(columns=[
                "user_id", "song_id", "interaction_type",
                "play_duration_sec", "completion_rate", "device_timestamp"
            ])
    logger.info(f"[MySQL] user_interactions: {len(df):,} rows")
    return df


def _fetch_mysql_likes(mysql_engine) -> pd.DataFrame:
    """Fetch like events from user_liked_songs."""
    logger.info("[MySQL] Fetching user_liked_songs...")
    query = text("""
        SELECT user_id, song_id, liked_at
        FROM user_liked_songs
    """)
    with mysql_engine.connect() as conn:
        rows = conn.execute(query).mappings().all()
        df = pd.DataFrame(rows)
        if df.empty:
            df = pd.DataFrame(columns=["user_id", "song_id", "liked_at"])
    logger.info(f"[MySQL] user_liked_songs: {len(df):,} rows")
    return df


def _fetch_mysql_songs(mysql_engine) -> pd.DataFrame:
    """Fetch song play counts from the songs table."""
    logger.info("[MySQL] Fetching songs (play_count)...")
    query = text("SELECT id AS song_id, play_count FROM songs")
    with mysql_engine.connect() as conn:
        rows = conn.execute(query).mappings().all()
        df = pd.DataFrame(rows)
        if df.empty:
            df = pd.DataFrame(columns=["song_id", "play_count"])
    # song_id in MySQL is likely a Long; cast to string to match JioSaavn IDs
    if not df.empty and "song_id" in df.columns:
        df["song_id"] = df["song_id"].astype(str)
    logger.info(f"[MySQL] songs: {len(df):,} rows")
    return df


# ── PostgreSQL queries ────────────────────────────────────────────────────────

def _fetch_pg_audio_features(pg_engine) -> pd.DataFrame:
    """Fetch language and decade from song_audio_features."""
    logger.info("[PG] Fetching song_audio_features (language, decade)...")
    query = text("SELECT song_id, language, decade FROM song_audio_features")
    with pg_engine.connect() as conn:
        rows = conn.execute(query).mappings().all()
        df = pd.DataFrame(rows)
        if df.empty:
            df = pd.DataFrame(columns=["song_id", "language", "decade"])
    logger.info(f"[PG] song_audio_features: {len(df):,} rows")
    return df


# ── Feature engineering ───────────────────────────────────────────────────────

def build_feature_matrix(
    interactions_df: pd.DataFrame,
    likes_df: pd.DataFrame,
    songs_df: pd.DataFrame,
    audio_features_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Builds one row PER INTERACTION EVENT (not per user-song pair).

    For each row, aggregate features (skip_count, user_play_count,
    completion_rate) are computed from all PRIOR interactions for
    that (user, song) — i.e., interactions with an earlier timestamp —
    to avoid including the current event in its own feature counts
    (leakage guard, see module docstring).

    tier_used is set to "unknown" for all historical rows because the
    recommendation-serving tier was never logged (see DATA HONESTY NOTE
    in module docstring).

    content_similarity_score is 0.0 for all historical rows for the same
    reason: without knowing which tier served a historical interaction,
    we cannot know the seed song, so no similarity can be computed.
    """
    logger.info("Building feature matrix (one row per interaction event)...")

    if interactions_df.empty:
        logger.warning("interactions_df is empty — returning empty dataset.")
        empty_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES + [TARGET_COL, "user_id", "song_id"]
        return pd.DataFrame(columns=empty_cols)

    # ── Ensure ID types and device_timestamp are consistent ─────────────────────
    interactions_df = interactions_df.copy()
    interactions_df["user_id"] = interactions_df["user_id"].astype(str)
    interactions_df["song_id"] = interactions_df["song_id"].astype(str)
    interactions_df["device_timestamp"] = pd.to_numeric(
        interactions_df["device_timestamp"], errors="coerce"
    ).fillna(0)

    likes_df = likes_df.copy()
    if not likes_df.empty:
        likes_df["user_id"] = likes_df["user_id"].astype(str)
        likes_df["song_id"] = likes_df["song_id"].astype(str)

    songs_df = songs_df.copy()
    if not songs_df.empty and "song_id" in songs_df.columns:
        songs_df["song_id"] = songs_df["song_id"].astype(str)

    audio_features_df = audio_features_df.copy()
    if not audio_features_df.empty and "song_id" in audio_features_df.columns:
        audio_features_df["song_id"] = audio_features_df["song_id"].astype(str)

    # Sort ascending so prior interactions come first (critical for leakage guard)
    interactions_df = interactions_df.sort_values(
        ["user_id", "song_id", "device_timestamp"], ascending=True
    ).reset_index(drop=True)

    # ── Pre-compute per-song like counts (global, not per-row) ────────────────
    # This is NOT leakage: likes are an external signal independent of the
    # individual interaction event we're building a row for.
    if not likes_df.empty:
        song_likes_count = (
            likes_df.groupby("song_id")["user_id"].count()
            .reset_index()
            .rename(columns={"user_id": "likes_count"})
        )
    else:
        song_likes_count = pd.DataFrame(columns=["song_id", "likes_count"])

    # ── Pre-compute popularity score (global, not per-row) ────────────────────
    if not songs_df.empty:
        songs_df = songs_df.copy()
        log_vals = songs_df["play_count"].apply(lambda x: math.log1p(max(x or 0, 0)))
        max_val = log_vals.max()
        songs_df["popularity_score"] = log_vals / max_val if max_val > 0 else log_vals
    else:
        songs_df = pd.DataFrame(columns=["song_id", "play_count", "popularity_score"])

    # ── Pre-compute user's favourite language and decade ──────────────────────
    # Computed from ALL interactions (not leakage — it's a user-level signal
    # that reflects long-term preference, not the specific event's type).
    if not audio_features_df.empty:
        merged_all = interactions_df.merge(
            audio_features_df[["song_id", "language", "decade"]],
            on="song_id",
            how="left",
        )
        user_fav_language = (
            merged_all.dropna(subset=["language"])
            .groupby(["user_id", "language"])
            .size()
            .reset_index(name="cnt")
            .sort_values("cnt", ascending=False)
            .drop_duplicates(subset=["user_id"])
            [["user_id", "language"]]
            .rename(columns={"language": "user_fav_language"})
        )
        user_fav_decade = (
            merged_all.dropna(subset=["decade"])
            .groupby(["user_id", "decade"])
            .size()
            .reset_index(name="cnt")
            .sort_values("cnt", ascending=False)
            .drop_duplicates(subset=["user_id"])
            [["user_id", "decade"]]
            .rename(columns={"decade": "user_fav_decade"})
        )
    else:
        logger.warning("No audio features available — genre/decade match will be 0.")
        user_fav_language = pd.DataFrame(columns=["user_id", "user_fav_language"])
        user_fav_decade = pd.DataFrame(columns=["user_id", "user_fav_decade"])

    # ── Build per-interaction rows with leakage-guarded aggregates ────────────
    rows = []
    now_ms = pd.Timestamp.now().timestamp() * 1000

    # Group by (user_id, song_id) for efficient prior-interaction lookups
    grouped = interactions_df.groupby(["user_id", "song_id"], sort=False)

    for (user_id, song_id), group in grouped:
        # Sort within group by timestamp (ascending = oldest first)
        group = group.sort_values("device_timestamp", ascending=True).reset_index(drop=True)

        for idx, row in group.iterrows():
            # All interactions for this (user, song) with timestamps STRICTLY BEFORE
            # the current row — these are the "prior history" features.
            current_ts = row["device_timestamp"]
            prior = group[group["device_timestamp"] < current_ts]

            # ── Leakage-guarded aggregates (from prior interactions only) ──────
            prior_plays = prior[prior["interaction_type"] == "play"]
            prior_skips = prior[prior["interaction_type"] == "skip"]

            user_play_count = len(prior_plays)
            skip_count = len(prior_skips)

            prior_completions = prior["completion_rate"].dropna()
            completion_rate = float(prior_completions.mean()) if len(prior_completions) > 0 else 0.0

            # ── Target: the score for THIS specific interaction event ──────────
            target_score = _score(
                row["interaction_type"],
                row["completion_rate"] if pd.notna(row["completion_rate"]) else 0.0,
            )

            # ── Recency: days since the most recent PRIOR interaction ──────────
            # (not the current one — using current_ts would give recency=0 always)
            if len(prior) > 0 and prior["device_timestamp"].max() > 0:
                last_prior_ts = prior["device_timestamp"].max()
                recency_days = (now_ms - last_prior_ts) / 86_400_000
            else:
                # No prior history — first-ever interaction for this (user, song)
                recency_days = 999.0

            rows.append({
                "user_id": user_id,
                "song_id": song_id,
                "user_play_count": user_play_count,
                "skip_count": skip_count,
                "completion_rate": completion_rate,
                "recency_days": recency_days,
                TARGET_COL: target_score,
                "_device_timestamp": current_ts,  # kept for debugging; dropped later
            })

    if not rows:
        logger.warning("No rows built — returning empty dataset.")
        empty_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES + [TARGET_COL, "user_id", "song_id"]
        return pd.DataFrame(columns=empty_cols)

    df = pd.DataFrame(rows)
    logger.info(f"Per-interaction rows built: {len(df):,}")

    # ── Merge global signals ──────────────────────────────────────────────────

    # Per-song like count
    df = df.merge(song_likes_count, on="song_id", how="left")
    df["likes_count"] = df["likes_count"].fillna(0).astype(int)

    # Popularity score
    if "popularity_score" in songs_df.columns:
        df = df.merge(songs_df[["song_id", "popularity_score"]], on="song_id", how="left")
        df["popularity_score"] = df["popularity_score"].fillna(0.0)
    else:
        df["popularity_score"] = 0.0

    # Language / decade match
    df = df.merge(user_fav_language, on="user_id", how="left")
    df = df.merge(user_fav_decade, on="user_id", how="left")

    if not audio_features_df.empty:
        df = df.merge(
            audio_features_df[["song_id", "language", "decade"]],
            on="song_id",
            how="left",
        )
        # Fix B: songs not in song_audio_features have no language/decade data.
        # Default genre_language_match to 0 (no match) rather than leaving null.
        # Known coverage gap: only songs in the content-model candidate pool have
        # audio features. All other songs default to 0 here.
        df["genre_language_match"] = (
            (df["language"].notna())
            & (df["user_fav_language"].notna())
            & (df["language"] == df["user_fav_language"])
        ).astype(int)
        df["decade_match"] = (
            (df["decade"].notna())
            & (df["user_fav_decade"].notna())
            & (df["decade"] == df["user_fav_decade"])
        ).astype(int)
    else:
        df["genre_language_match"] = 0
        df["decade_match"] = 0

    # ── Fix 1: tier_used = "unknown" for ALL historical rows ─────────────────
    # We do NOT attempt to reconstruct which tier served a historical interaction.
    # The recommendation-serving tier was never logged. Retroactively applying
    # today's tier-selection logic would produce historically inaccurate values.
    # See DATA HONESTY NOTE in the module docstring and README.md.
    df["tier_used"] = "unknown"

    # ── Fix 2: content_similarity_score = 0.0 for ALL historical rows ─────────
    # Without knowing the tier, we don't know the seed song, so no similarity
    # score can be computed. This is consistent with the original spec's handling
    # of non-content-based recommendations — extended to "unknown tier" rows.
    df["content_similarity_score"] = 0.0

    # ── Select and validate final columns ─────────────────────────────────────
    final_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES + [TARGET_COL, "user_id", "song_id"]
    df = df[final_cols].copy()

    # Drop rows with null targets (should not occur, but defensive)
    before = len(df)
    df = df.dropna(subset=[TARGET_COL])
    after = len(df)
    if before != after:
        logger.warning(f"Dropped {before - after} rows with null target scores.")

    logger.info(
        f"Feature matrix built: {len(df):,} rows × {len(df.columns)} columns\n"
        f"  tier_used distribution:\n{df['tier_used'].value_counts().to_string()}\n"
        f"  (All rows are 'unknown' — see DATA HONESTY NOTE in module docstring)\n"
        f"  Target score stats:\n{df[TARGET_COL].describe().to_string()}"
    )
    return df


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    logger.info("=== MforMusic Explainability Dataset Builder ===")

    # Connect to databases
    try:
        mysql_engine = _get_mysql_engine()
        logger.info("MySQL connection established.")
    except Exception as e:
        logger.error(f"MySQL connection failed: {e}")
        sys.exit(1)

    try:
        pg_engine = _get_pg_engine()
        logger.info("PostgreSQL connection established.")
    except Exception as e:
        logger.error(f"PostgreSQL connection failed: {e}")
        sys.exit(1)

    # Fetch raw data
    try:
        interactions_df = _fetch_mysql_interactions(mysql_engine)
        likes_df = _fetch_mysql_likes(mysql_engine)
        songs_df = _fetch_mysql_songs(mysql_engine)
        audio_features_df = _fetch_pg_audio_features(pg_engine)
    except Exception as e:
        logger.error(f"Data fetch failed: {e}", exc_info=True)
        sys.exit(1)

    if interactions_df.empty:
        logger.warning(
            "No interactions found — dataset will be empty. "
            "Make sure the MySQL database has data before running this script."
        )

    # Build feature matrix
    try:
        df = build_feature_matrix(interactions_df, likes_df, songs_df, audio_features_df)
    except Exception as e:
        logger.error(f"Feature engineering failed: {e}", exc_info=True)
        sys.exit(1)

    # Validate
    assert set(NUMERIC_FEATURES + CATEGORICAL_FEATURES + [TARGET_COL]).issubset(
        df.columns
    ), "Missing expected columns in dataset!"

    # Save
    df.to_parquet(OUTPUT_PATH, index=False)
    logger.info(f"Dataset saved → {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size / 1024:.1f} KB)")
    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
