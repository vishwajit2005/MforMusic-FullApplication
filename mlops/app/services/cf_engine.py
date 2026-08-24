"""
Collaborative Filtering Engine — ALS (Alternating Least Squares)

Uses the `implicit` library, purpose-built for implicit feedback datasets
(plays, skips, likes — where absence of an interaction ≠ dislike).

Interaction scoring strategy:
  PLAY     → completion_rate × 3.0  (max 3.0 for a full listen; 0.1 minimum)
  LIKE     → 4.0  (explicit strong positive)
  DOWNLOAD → 3.5  (user wants offline access — very high intent)
  PLAYLIST_ADD → 3.0  (intentional curation)
  SKIP     → negative signal — stored but clamped to 0.01 for ALS confidence matrix
             (ALS works best with non-negative confidence values; we store the
              raw negative score and track it separately for future penalty logic)
  UNLIKE   → negative — clamped to 0.01

Thread safety: all reads/writes to model state go through _lock (RLock).
"""

import logging
import threading

import numpy as np
import scipy.sparse as sparse
from implicit.als import AlternatingLeastSquares
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.models.interaction import Interaction

logger = logging.getLogger(__name__)


# ── Interaction weight lookup ─────────────────────────────────────────────────

def _compute_score(interaction_type: str, completion_rate: float) -> float:
    """
    Maps an interaction event to a confidence weight for the ALS matrix.
    ALS is trained on confidence values (non-negative), so negative interactions
    are clamped to a near-zero positive value rather than truly negative.
    """
    itype = (interaction_type or "").lower().strip()

    if itype == "play":
        # Full listen = 3.0; brief tap = 0.1; linear scaling in between
        return max(0.1, float(completion_rate) * 3.0)
    elif itype == "like":
        return 4.0
    elif itype == "download":
        return 3.5
    elif itype == "playlist_add":
        return 3.0
    elif itype == "skip":
        # Negative signal — clamp for ALS confidence matrix
        return 0.01
    elif itype == "unlike":
        return 0.01
    else:
        return 0.5  # unknown interaction type — treat as weak positive


# ── Engine ────────────────────────────────────────────────────────────────────

class CollaborativeFilterEngine:
    """
    Thread-safe ALS-based collaborative filter.

    Lifecycle:
      1. Call train(db) on startup to load history from PostgreSQL.
      2. TelemetryService calls trigger_retrain() after every N interactions.
      3. APScheduler calls trigger_retrain() hourly.
      4. recommend_for_user() / get_popular_songs() serve predictions.
    """

    def __init__(self, factors: int = 64, iterations: int = 50, regularization: float = 0.01):
        self._factors = factors
        self._iterations = iterations
        self._regularization = regularization

        # ── Model state (protected by _lock) ─────────────────────────────────
        self._lock = threading.RLock()
        self._model: AlternatingLeastSquares | None = None
        self._user_item_matrix: sparse.csr_matrix | None = None

        # Bidirectional index maps: string ID ↔ integer matrix index
        self._user_index: dict[str, int] = {}        # user_id  → row index
        self._item_index: dict[str, int] = {}        # song_id  → col index
        self._rev_item_index: dict[int, str] = {}    # col index → song_id

        self._model_version: str = "untrained"
        self._total_interactions: int = 0
        self._total_users: int = 0
        self._total_songs: int = 0

        # Retraining state
        self._retrain_lock = threading.Lock()
        self._is_retraining: bool = False

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_trained(self) -> bool:
        with self._lock:
            return self._model is not None

    @property
    def model_version(self) -> str:
        with self._lock:
            return self._model_version

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "trained": self._model is not None,
                "model_version": self._model_version,
                "total_interactions": self._total_interactions,
                "total_users": self._total_users,
                "total_songs": self._total_songs,
            }

    def train(self, db: Session) -> bool:
        """
        Full retrain from all interactions in PostgreSQL.
        Thread-safe — only one retrain runs at a time.
        Returns True on success, False if not enough data.
        """
        with self._retrain_lock:
            if self._is_retraining:
                logger.info("Retrain already in progress — skipping duplicate trigger.")
                return False
            self._is_retraining = True

        try:
            return self._train_internal(db)
        finally:
            with self._retrain_lock:
                self._is_retraining = False

    def trigger_retrain(self):
        """
        Non-blocking retrain trigger — spawns a daemon thread.
        Safe to call from request handlers.
        """
        def _retrain_worker():
            from app.core.database import SessionLocal
            db = SessionLocal()
            try:
                self.train(db)
            finally:
                db.close()

        t = threading.Thread(target=_retrain_worker, name="cf-retrain", daemon=True)
        t.start()
        logger.info("CF retrain triggered in background thread.")

    def recommend_for_user(self, user_id: str, n: int = 20) -> list[dict]:
        """
        Returns top-N ALS recommendations for a known user.
        Returns [] if user is unknown (cold start — caller handles fallback).
        """
        with self._lock:
            if self._model is None:
                return []
            if user_id not in self._user_index:
                return []

            user_row = self._user_index[user_id]
            user_vector = self._user_item_matrix[user_row]

            try:
                item_ids, scores = self._model.recommend(
                    user_row,
                    user_vector,
                    N=n,
                    filter_already_liked_items=True,
                )
            except Exception as e:
                logger.error(f"ALS recommend() failed for user {user_id}: {e}")
                return []

            results = []
            for rank, (item_idx, score) in enumerate(
                zip(item_ids.tolist(), scores.tolist()), start=1
            ):
                song_id = self._rev_item_index.get(int(item_idx))
                if song_id:
                    results.append({"song_id": song_id, "score": round(float(score), 6), "rank": rank})

            return results

    def get_popular_songs(self, db: Session, n: int = 20) -> list[dict]:
        """
        Cold-start fallback: globally most-interacted songs weighted by type.
        Computes directly from the interactions table — no model needed.
        """
        weight_expr = case(
            (Interaction.interaction_type == "like", 4.0),
            (Interaction.interaction_type == "download", 3.5),
            (Interaction.interaction_type == "playlist_add", 3.0),
            (Interaction.interaction_type == "play", 1.0),
            else_=0.1,
        )

        rows = (
            db.query(
                Interaction.song_id,
                func.sum(weight_expr).label("score"),
            )
            .group_by(Interaction.song_id)
            .order_by(func.sum(weight_expr).desc())
            .limit(n)
            .all()
        )

        return [
            {"song_id": row.song_id, "score": round(float(row.score), 4), "rank": i + 1}
            for i, row in enumerate(rows)
        ]

    # ── Internal training logic ───────────────────────────────────────────────

    def _train_internal(self, db: Session) -> bool:
        logger.info("CF model training started...")

        try:
            interactions = db.query(Interaction).all()
        except Exception as e:
            logger.error(f"Failed to fetch interactions from DB: {e}")
            return False

        if not interactions:
            logger.warning("No interactions in DB — skipping training.")
            return False

        # Collect unique users and songs
        users = sorted({i.user_id for i in interactions})
        songs = sorted({i.song_id for i in interactions})

        if len(users) < 2 or len(songs) < 2:
            logger.warning(
                f"Insufficient data: {len(users)} user(s), {len(songs)} song(s). "
                "Need ≥ 2 of each to train."
            )
            return False

        user_index = {u: idx for idx, u in enumerate(users)}
        item_index = {s: idx for idx, s in enumerate(songs)}
        rev_item_index = {idx: s for s, idx in item_index.items()}

        # Build sparse confidence matrix (cumulative per user-song pair)
        pair_scores: dict[tuple[int, int], float] = {}
        for interaction in interactions:
            u_idx = user_index[interaction.user_id]
            i_idx = item_index[interaction.song_id]
            score = _compute_score(
                interaction.interaction_type,
                interaction.completion_rate or 0.0,
            )
            key = (u_idx, i_idx)
            pair_scores[key] = pair_scores.get(key, 0.0) + score

        rows, cols, data = [], [], []
        for (u_idx, i_idx), score in pair_scores.items():
            rows.append(u_idx)
            cols.append(i_idx)
            # ALS requires positive confidence values — clamp to minimum 0.01
            data.append(max(0.01, score))

        user_item_matrix = sparse.csr_matrix(
            (data, (rows, cols)),
            shape=(len(users), len(songs)),
            dtype=np.float32,
        )

        # Train ALS
        # factors capped at (num_items - 1) to avoid rank deficiency
        actual_factors = min(self._factors, len(songs) - 1)
        model = AlternatingLeastSquares(
            factors=actual_factors,
            regularization=self._regularization,
            iterations=self._iterations,
            use_gpu=False,
        )

        try:
            model.fit(user_item_matrix, show_progress=False)
        except Exception as e:
            logger.error(f"ALS fit() failed: {e}", exc_info=True)
            return False

        version_tag = (
            f"v_{len(interactions)}i_{len(users)}u_{len(songs)}s"
        )

        # Atomic state swap under lock — zero downtime during retrain
        with self._lock:
            self._model = model
            self._user_item_matrix = user_item_matrix
            self._user_index = user_index
            self._item_index = item_index
            self._rev_item_index = rev_item_index
            self._model_version = version_tag
            self._total_interactions = len(interactions)
            self._total_users = len(users)
            self._total_songs = len(songs)

        logger.info(
            f"CF model trained ✓ | {len(users)} users | {len(songs)} songs | "
            f"{len(interactions)} interactions | factors={actual_factors} | "
            f"version={version_tag}"
        )
        return True


# ── Module-level singleton ────────────────────────────────────────────────────
cf_engine = CollaborativeFilterEngine()
