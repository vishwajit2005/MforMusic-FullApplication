"""
Content-Based Recommendation Service

Uses an offline-trained cosine NearestNeighbors model and audio + metadata features
scraped from the JioSaavn catalog to provide similarity-based recommendations for
cold-start users (who have interaction history but not enough for Collaborative Filtering).

Supports organic model growth and automatic, thread-safe retraining with hot-swapping.
"""

import logging
import os
import threading
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.song_audio_feature import SongAudioFeature, FEATURE_COLUMNS_63

logger = logging.getLogger(__name__)


class ContentRecommendationService:
    """
    Singleton engine for content-based similarity recommendations.
    Loads pre-trained artifacts once at startup, performs in-memory
    k-NN vector queries, and supports atomic background retraining.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._is_ready: bool = False
        self._is_retraining: bool = False
        self._model_version: str = "content_knn_uninitialized"

        # Model artifacts
        self._nn_model: Any = None
        self._scaler: Any = None
        self._language_encoder: Any = None
        self._decade_encoder: Any = None

        # Data & Index mappings
        self._features_matrix: np.ndarray | None = None
        self._track_ids: list[str] = []
        self._track_id_to_idx: dict[str, int] = {}
        self._idx_to_track_id: dict[int, str] = {}
        self._track_metadata: dict[str, dict[str, Any]] = {}

    @property
    def is_ready(self) -> bool:
        with self._lock:
            return self._is_ready

    @property
    def is_retraining(self) -> bool:
        with self._lock:
            return self._is_retraining

    @property
    def model_version(self) -> str:
        with self._lock:
            return self._model_version

    @property
    def total_tracks(self) -> int:
        with self._lock:
            return len(self._track_ids)

    @property
    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ready": self._is_ready,
                "retraining": self._is_retraining,
                "model_version": self._model_version,
                "total_tracks": len(self._track_ids),
            }

    def has_track(self, track_id: str) -> bool:
        """Checks if a track exists in the content-based candidate pool."""
        with self._lock:
            return self._is_ready and track_id in self._track_id_to_idx

    def get_track_metadata(self, track_id: str) -> dict[str, Any] | None:
        """Returns metadata (title, artist, album, etc.) for a track if available."""
        with self._lock:
            if not self._is_ready:
                return None
            return self._track_metadata.get(str(track_id))

    def _resolve_model_dir(self, model_dir_path: str | Path) -> Path:
        """Resolves model directory path relative to current working directory or app root."""
        p = Path(model_dir_path)
        if p.is_absolute() and p.exists():
            return p

        # Check relative to cwd
        if p.exists():
            return p.resolve()

        # Check relative to app root (parent of services/ directory)
        app_root = Path(__file__).resolve().parent.parent
        candidate = app_root / model_dir_path
        if candidate.exists():
            return candidate.resolve()

        # Check relative to mlops root
        mlops_root = app_root.parent
        candidate_mlops = mlops_root / model_dir_path
        if candidate_mlops.exists():
            return candidate_mlops.resolve()

        return p.resolve()

    def load_artifacts(self, model_dir_path: str | Path | None = None) -> bool:
        """
        Loads the offline model artifacts from disk into memory.
        Safe to call during FastAPI lifespan startup.
        """
        settings = get_settings()
        dir_to_use = model_dir_path or settings.CONTENT_MODEL_DIR
        resolved_dir = self._resolve_model_dir(dir_to_use)

        logger.info(f"Loading content-based model artifacts from: {resolved_dir}")

        if not resolved_dir.exists() or not resolved_dir.is_dir():
            logger.warning(
                f"Content model directory '{resolved_dir}' does not exist. "
                "Content-based recommendation tier will remain disabled until artifacts are placed."
            )
            with self._lock:
                self._is_ready = False
            return False

        # Required artifact paths
        nn_path = resolved_dir / "nn_model.joblib"
        scaler_path = resolved_dir / "scaler.joblib"
        lang_path = resolved_dir / "language_encoder.joblib"
        decade_path = resolved_dir / "decade_encoder.joblib"
        features_path = resolved_dir / "combined_features.csv"
        track_index_path = resolved_dir / "track_index.csv"

        missing = [
            p.name for p in (nn_path, scaler_path, lang_path, decade_path, features_path, track_index_path)
            if not p.exists()
        ]

        if missing:
            logger.warning(
                f"Content-based model artifacts incomplete in '{resolved_dir}'. "
                f"Missing files: {missing}. Content-based tier will remain disabled."
            )
            with self._lock:
                self._is_ready = False
            return False

        try:
            # 1. Load joblib models
            nn_model = joblib.load(nn_path)
            scaler = joblib.load(scaler_path)
            lang_encoder = joblib.load(lang_path)
            decade_encoder = joblib.load(decade_path)

            # 2. Load feature matrix
            features_df = pd.read_csv(features_path)

            # Identify track ID column
            track_id_col = None
            for col in ["external_track_id", "track_id", "song_id"]:
                if col in features_df.columns:
                    track_id_col = col
                    break

            if track_id_col:
                track_ids = features_df[track_id_col].astype(str).tolist()
                numeric_df = features_df.drop(columns=[track_id_col])
            else:
                track_ids = [str(x) for x in features_df.index]
                numeric_df = features_df

            features_matrix = numeric_df.select_dtypes(include=[np.number]).to_numpy(dtype=np.float32)

            # 3. Load track metadata index
            track_metadata: dict[str, dict[str, Any]] = {}
            try:
                meta_df = pd.read_csv(track_index_path)
                meta_id_col = None
                for col in ["external_track_id", "track_id", "song_id"]:
                    if col in meta_df.columns:
                        meta_id_col = col
                        break

                if meta_id_col:
                    for _, row in meta_df.iterrows():
                        tid = str(row[meta_id_col])
                        track_metadata[tid] = row.to_dict()
            except Exception as e:
                logger.warning(f"Could not parse track_index.csv metadata: {e}")

            # 4. Build index mapping
            track_id_to_idx = {tid: idx for idx, tid in enumerate(track_ids)}
            idx_to_track_id = {idx: tid for idx, tid in enumerate(track_ids)}

            version_tag = f"content_knn_v1_{len(track_ids)}s"

            with self._lock:
                self._nn_model = nn_model
                self._scaler = scaler
                self._language_encoder = lang_encoder
                self._decade_encoder = decade_encoder
                self._features_matrix = features_matrix
                self._track_ids = track_ids
                self._track_id_to_idx = track_id_to_idx
                self._idx_to_track_id = idx_to_track_id
                self._track_metadata = track_metadata
                self._model_version = version_tag
                self._is_ready = True

            logger.info(
                f"Content-based recommendation model loaded successfully: "
                f"{version_tag} ({len(track_ids)} candidate songs)"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to load content model artifacts from '{resolved_dir}': {e}", exc_info=True)
            with self._lock:
                self._is_ready = False
            return False

    def get_similar_songs(
        self,
        seed_track_id: str,
        n: int = 20,
        exclude_ids: set[str] | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Finds the top-N nearest neighbors for a given seed track using the pre-fitted
        NearestNeighbors model (cosine metric).
        """
        with self._lock:
            if not self._is_ready or self._nn_model is None or self._features_matrix is None:
                return []

            seed_str = str(seed_track_id)
            if seed_str not in self._track_id_to_idx:
                logger.debug(f"Seed track '{seed_str}' not in content-based candidate pool.")
                return []

            seed_idx = self._track_id_to_idx[seed_str]
            exclude_set = set(str(x) for x in (exclude_ids or []))
            exclude_set.add(seed_str)

            try:
                seed_vector = self._features_matrix[seed_idx].reshape(1, -1)
                total_candidates = len(self._track_ids)
                k_query = min(n + len(exclude_set) + 5, total_candidates)

                distances, indices = self._nn_model.kneighbors(seed_vector, n_neighbors=k_query)

                results = []
                for idx, dist in zip(indices[0], distances[0]):
                    candidate_id = self._idx_to_track_id.get(int(idx))
                    if not candidate_id or candidate_id in exclude_set:
                        continue

                    # Cosine distance = 1.0 - cosine_similarity
                    similarity_score = max(0.0, 1.0 - float(dist))
                    results.append({
                        "song_id": candidate_id,
                        "score": round(similarity_score, 4),
                        "rank": len(results) + 1,
                    })

                    if len(results) >= n:
                        break

                return results

            except Exception as e:
                logger.error(f"Error querying nearest neighbors for seed '{seed_str}': {e}", exc_info=True)
                return []

    # ── Retraining & Hot-Swap Engine ──────────────────────────────────────────

    def trigger_retrain(self, force: bool = False):
        """Non-blocking: kicks off background content-based model retraining."""
        def _worker():
            from app.core.database import SessionLocal
            db = SessionLocal()
            try:
                self.train(db, force=force)
            finally:
                db.close()

        t = threading.Thread(target=_worker, name="content-retrain-bg", daemon=True)
        t.start()

    def train(self, db: Session, force: bool = False) -> bool:
        """
        Retrains the content-based similarity model by merging newly extracted
        features from PostgreSQL song_audio_features with the baseline dataset.
        Atomically hot-swaps under RLock with zero downtime.
        """
        settings = get_settings()

        with self._lock:
            if self._is_retraining:
                logger.info("Content model retraining already in progress — skipping.")
                return False
            self._is_retraining = True

        try:
            logger.info("Checking for new extracted audio features...")
            # Query un-incorporated rows
            new_features_rows = (
                db.query(SongAudioFeature)
                .filter(SongAudioFeature.incorporated_in_model == False)  # noqa: E712
                .all()
            )

            new_count = len(new_features_rows)
            logger.info(f"Found {new_count} new un-incorporated audio feature rows.")

            if new_count < settings.MIN_NEW_SONGS_FOR_CONTENT_RETRAIN and not force:
                logger.info(
                    f"New songs ({new_count}) < threshold ({settings.MIN_NEW_SONGS_FOR_CONTENT_RETRAIN}). "
                    "Skipping content retraining."
                )
                return False

            if new_count == 0 and not force:
                return False

            # Model directory
            resolved_dir = self._resolve_model_dir(settings.CONTENT_MODEL_DIR)
            resolved_dir.mkdir(parents=True, exist_ok=True)
            track_index_path = resolved_dir / "track_index.csv"
            features_path = resolved_dir / "combined_features.csv"

            if not track_index_path.exists():
                logger.warning(f"Baseline track_index.csv not found at {track_index_path}. Cannot retrain.")
                return False

            # Load existing base metadata and features
            base_meta_df = pd.read_csv(track_index_path)

            # Build list of new track dicts and feature dicts
            new_meta_records = []
            new_feature_records = []

            for row in new_features_rows:
                song_id = str(row.song_id)
                # Metadata
                meta_item = {
                    "external_track_id": song_id,
                    "title": row.title or song_id,
                    "artist": row.artist_name or "Unknown Artist",
                    "album": row.album or "Unknown Album",
                    "language": (row.language or "unknown").lower(),
                    "decade": row.decade or "2020s",
                }
                new_meta_records.append(meta_item)

                # 63 features
                feat_dict = {"external_track_id": song_id}
                for col in FEATURE_COLUMNS_63:
                    feat_dict[col] = getattr(row, col, 0.0)
                feat_dict["language"] = (row.language or "unknown").lower()
                feat_dict["decade"] = row.decade or "2020s"
                new_feature_records.append(feat_dict)

            # Deduplicate by external_track_id against baseline
            existing_ids = set(base_meta_df["external_track_id"].astype(str).tolist())
            unique_new_meta = [m for m in new_meta_records if m["external_track_id"] not in existing_ids]
            unique_new_feats = [f for f in new_feature_records if f["external_track_id"] not in existing_ids]

            if not unique_new_feats and not force:
                logger.info("All new features were already in dataset — marking incorporated.")
                for row in new_features_rows:
                    row.incorporated_in_model = True
                db.commit()
                return False

            # Merge metadata
            if unique_new_meta:
                new_meta_df = pd.DataFrame(unique_new_meta)
                combined_meta_df = pd.concat([base_meta_df, new_meta_df], ignore_index=True)
            else:
                combined_meta_df = base_meta_df

            # If combined_features.csv exists, load it
            current_combined_df = pd.read_csv(features_path) if features_path.exists() else None

            # Process new features
            # Load existing scaler and encoders
            scaler_path = resolved_dir / "scaler.joblib"
            lang_path = resolved_dir / "language_encoder.joblib"
            decade_path = resolved_dir / "decade_encoder.joblib"

            scaler = joblib.load(scaler_path) if scaler_path.exists() else StandardScaler()
            lang_encoder = joblib.load(lang_path) if lang_path.exists() else OneHotEncoder(handle_unknown="ignore")
            decade_encoder = joblib.load(decade_path) if decade_path.exists() else OneHotEncoder(handle_unknown="ignore")

            # Transform unique new tracks
            new_transformed_dfs = []
            if unique_new_feats:
                new_raw_df = pd.DataFrame(unique_new_feats)
                # Scale 63 audio features
                scaled_audio = scaler.transform(new_raw_df[FEATURE_COLUMNS_63].values)
                scaled_audio_df = pd.DataFrame(scaled_audio, columns=FEATURE_COLUMNS_63)

                # One-hot encode language & decade
                lang_raw = lang_encoder.transform(new_raw_df[["language"]].values)
                lang_onehot = (lang_raw.toarray() if hasattr(lang_raw, "toarray") else lang_raw) * 0.5
                lang_cols = [f"lang_{c}" for c in lang_encoder.categories_[0]]
                lang_df = pd.DataFrame(lang_onehot, columns=lang_cols)

                decade_raw = decade_encoder.transform(new_raw_df[["decade"]].values)
                decade_onehot = (decade_raw.toarray() if hasattr(decade_raw, "toarray") else decade_raw) * 0.3
                decade_cols = [f"decade_{c}" for c in decade_encoder.categories_[0]]
                decade_df = pd.DataFrame(decade_onehot, columns=decade_cols)

                # Combine
                new_feat_row_df = pd.concat([
                    pd.Series(new_raw_df["external_track_id"], name="external_track_id"),
                    scaled_audio_df,
                    lang_df,
                    decade_df
                ], axis=1)

                new_transformed_dfs.append(new_feat_row_df)

            if current_combined_df is not None and new_transformed_dfs:
                final_combined_df = pd.concat([current_combined_df] + new_transformed_dfs, ignore_index=True)
            elif current_combined_df is not None:
                final_combined_df = current_combined_df
            elif new_transformed_dfs:
                final_combined_df = pd.concat(new_transformed_dfs, ignore_index=True)
            else:
                final_combined_df = pd.DataFrame()

            # Ensure track_id column is dropped for training matrix
            track_ids = final_combined_df["external_track_id"].astype(str).tolist()
            numeric_matrix = final_combined_df.drop(columns=["external_track_id"]).select_dtypes(include=[np.number]).to_numpy(dtype=np.float32)

            # Fit NearestNeighbors
            logger.info(f"Fitting NearestNeighbors model on {len(track_ids)} tracks (matrix shape: {numeric_matrix.shape})...")
            new_nn_model = NearestNeighbors(
                metric="cosine",
                algorithm="brute",
                n_neighbors=min(20, len(track_ids)),
            )
            new_nn_model.fit(numeric_matrix)

            # Save updated artifacts to disk
            logger.info(f"Saving updated artifacts to {resolved_dir}...")
            joblib.dump(new_nn_model, resolved_dir / "nn_model.joblib")
            final_combined_df.to_csv(features_path, index=False)
            combined_meta_df.to_csv(track_index_path, index=False)

            # Mark processed rows as incorporated in PostgreSQL
            for row in new_features_rows:
                row.incorporated_in_model = True
            db.commit()
            logger.info(f"Marked {len(new_features_rows)} rows as incorporated in PostgreSQL.")

            # Build metadata dict
            track_metadata: dict[str, dict[str, Any]] = {}
            for _, r in combined_meta_df.iterrows():
                track_metadata[str(r["external_track_id"])] = r.to_dict()

            track_id_to_idx = {tid: idx for idx, tid in enumerate(track_ids)}
            idx_to_track_id = {idx: tid for idx, tid in enumerate(track_ids)}
            version_tag = f"content_knn_v2_{len(track_ids)}s"

            # ── Atomic in-memory hot swap under RLock ──────────────────────────
            with self._lock:
                self._nn_model = new_nn_model
                self._scaler = scaler
                self._language_encoder = lang_encoder
                self._decade_encoder = decade_encoder
                self._features_matrix = numeric_matrix
                self._track_ids = track_ids
                self._track_id_to_idx = track_id_to_idx
                self._idx_to_track_id = idx_to_track_id
                self._track_metadata = track_metadata
                self._model_version = version_tag
                self._is_ready = True

            logger.info(f"Content-based model retraining and hot-swap complete ✓ (version={version_tag})")
            return True

        except Exception as e:
            logger.error(f"Content model retraining failed: {e}", exc_info=True)
            db.rollback()
            return False
        finally:
            with self._lock:
                self._is_retraining = False


# Global singleton instance
content_service = ContentRecommendationService()
