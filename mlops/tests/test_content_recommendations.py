"""
Unit & Integration tests for ContentRecommendationService and 3-Tier Fallback
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler, OneHotEncoder

from app.services.content_recommendation_service import ContentRecommendationService
from app.schemas.recommendation import RecommendationResponse, SongRecommendation


class TestContentRecommendationService(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for synthetic model artifacts
        self.test_dir = tempfile.mkdtemp()
        self.model_dir = Path(self.test_dir)

        # 5 sample tracks
        self.track_ids = ["track_A", "track_B", "track_C", "track_D", "track_E"]
        np.random.seed(42)
        features = np.array([
            [1.0, 0.0, 0.5],
            [0.9, 0.1, 0.4],  # Similar to A
            [0.1, 0.9, 0.2],  # Dissimilar to A
            [0.85, 0.15, 0.45], # Very similar to A
            [0.0, 1.0, 0.0],  # Dissimilar to A
        ], dtype=np.float32)

        # Fit NearestNeighbors (cosine metric)
        nn = NearestNeighbors(metric="cosine", n_neighbors=4)
        nn.fit(features)

        # Fit dummy scaler & encoders
        scaler = StandardScaler().fit(features[:, :2])
        lang_enc = OneHotEncoder().fit([["hindi"], ["english"], ["tamil"], ["hindi"], ["telugu"]])
        decade_enc = OneHotEncoder().fit([["2020s"], ["2020s"], ["2010s"], ["2020s"], ["2000s"]])

        # Save artifacts
        joblib.dump(nn, self.model_dir / "nn_model.joblib")
        joblib.dump(scaler, self.model_dir / "scaler.joblib")
        joblib.dump(lang_enc, self.model_dir / "language_encoder.joblib")
        joblib.dump(decade_enc, self.model_dir / "decade_encoder.joblib")

        # Save combined_features.csv
        df = pd.DataFrame(features, columns=["feat1", "feat2", "feat3"])
        df.insert(0, "external_track_id", self.track_ids)
        df.to_csv(self.model_dir / "combined_features.csv", index=False)

        # Save track_index.csv
        meta_df = pd.DataFrame({
            "external_track_id": self.track_ids,
            "title": ["Song A", "Song B", "Song C", "Song D", "Song E"],
            "artist": ["Artist 1", "Artist 1", "Artist 2", "Artist 3", "Artist 4"],
        })
        meta_df.to_csv(self.model_dir / "track_index.csv", index=False)

        self.service = ContentRecommendationService()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_load_artifacts_success(self):
        loaded = self.service.load_artifacts(self.model_dir)
        self.assertTrue(loaded)
        self.assertTrue(self.service.is_ready)
        self.assertEqual(self.service.total_tracks, 5)
        self.assertTrue(self.service.has_track("track_A"))
        self.assertFalse(self.service.has_track("unknown_track"))
        self.assertEqual(self.service.model_version, "content_knn_v1_5s")

    def test_get_similar_songs_ranks_correctly(self):
        self.service.load_artifacts(self.model_dir)
        recs = self.service.get_similar_songs(seed_track_id="track_A", n=3)

        self.assertTrue(len(recs) > 0)
        # Seed track itself should never be included in results
        self.assertNotIn("track_A", [r["song_id"] for r in recs])

        # Track B and D should have highest similarity scores
        top_ids = [r["song_id"] for r in recs[:2]]
        self.assertIn("track_B", top_ids)
        self.assertIn("track_D", top_ids)

        # Ranks must be 1, 2, 3...
        self.assertEqual(recs[0]["rank"], 1)
        self.assertTrue(recs[0]["score"] >= recs[1]["score"])

    def test_get_similar_songs_with_exclude_ids(self):
        self.service.load_artifacts(self.model_dir)
        # Exclude track_B
        recs = self.service.get_similar_songs(seed_track_id="track_A", n=3, exclude_ids={"track_B"})
        rec_ids = [r["song_id"] for r in recs]

        self.assertNotIn("track_A", rec_ids)
        self.assertNotIn("track_B", rec_ids)
        self.assertIn("track_D", rec_ids)

    def test_unknown_seed_returns_empty_list_cleanly(self):
        self.service.load_artifacts(self.model_dir)
        recs = self.service.get_similar_songs(seed_track_id="non_existent_id", n=10)
        self.assertEqual(recs, [])

    def test_uninitialized_service_returns_empty_list(self):
        uninit_service = ContentRecommendationService()
        recs = uninit_service.get_similar_songs(seed_track_id="track_A", n=10)
        self.assertEqual(recs, [])
        self.assertFalse(uninit_service.is_ready)

    def test_missing_files_fails_gracefully(self):
        # Empty temp dir
        empty_dir = tempfile.mkdtemp()
        try:
            res = self.service.load_artifacts(empty_dir)
            self.assertFalse(res)
            self.assertFalse(self.service.is_ready)
        finally:
            shutil.rmtree(empty_dir)

    def test_response_schema_compatibility(self):
        self.service.load_artifacts(self.model_dir)
        recs = self.service.get_similar_songs(seed_track_id="track_A", n=2)
        response_data = {
            "user_id": "test_user_123",
            "recommendations": recs,
            "model_version": self.service.model_version,
            "total": len(recs),
            "source": "content_based",
        }
        # Validate Pydantic model parses successfully
        parsed = RecommendationResponse(**response_data)
        self.assertEqual(parsed.source, "content_based")
        self.assertEqual(len(parsed.recommendations), len(recs))


class TestRecommendationServiceFallback(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.model_dir = Path(self.test_dir)

        # 5 sample tracks
        self.track_ids = ["jio_101", "jio_102", "jio_103", "jio_104", "jio_105"]
        features = np.array([
            [1.0, 0.0],
            [0.9, 0.1],
            [0.1, 0.9],
            [0.8, 0.2],
            [0.0, 1.0],
        ], dtype=np.float32)

        nn = NearestNeighbors(metric="cosine", n_neighbors=4)
        nn.fit(features)
        scaler = StandardScaler().fit(features)
        lang_enc = OneHotEncoder().fit([["hi"], ["hi"], ["en"], ["hi"], ["en"]])
        decade_enc = OneHotEncoder().fit([["20s"], ["20s"], ["10s"], ["20s"], ["00s"]])

        joblib.dump(nn, self.model_dir / "nn_model.joblib")
        joblib.dump(scaler, self.model_dir / "scaler.joblib")
        joblib.dump(lang_enc, self.model_dir / "language_encoder.joblib")
        joblib.dump(decade_enc, self.model_dir / "decade_encoder.joblib")

        df = pd.DataFrame(features, columns=["f1", "f2"])
        df.insert(0, "external_track_id", self.track_ids)
        df.to_csv(self.model_dir / "combined_features.csv", index=False)

        meta_df = pd.DataFrame({"external_track_id": self.track_ids, "title": ["T1", "T2", "T3", "T4", "T5"]})
        meta_df.to_csv(self.model_dir / "track_index.csv", index=False)

        from app.services.content_recommendation_service import content_service
        self.content_service = content_service
        self.content_service.load_artifacts(self.model_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_content_based_middle_tier_selection(self):
        from unittest.mock import MagicMock
        from app.services.recommendation_service import get_recommendations
        from app.services.cf_engine import cf_engine

        # Mock DB session and interactions
        mock_db = MagicMock()
        mock_interaction = MagicMock()
        mock_interaction.user_id = "user_42"
        mock_interaction.song_id = "jio_101"
        mock_interaction.interaction_type = "like"

        # User has 1 interaction (< MIN_INTERACTIONS_FOR_CF)
        mock_query = mock_db.query.return_value.filter.return_value.order_by.return_value
        mock_query.all.return_value = [mock_interaction]

        # CF is not trained or user not eligible
        cf_engine._is_trained = False

        result = get_recommendations(user_id="user_42", db=mock_db, n=3)

        self.assertEqual(result["source"], "content_based")
        self.assertEqual(result["user_id"], "user_42")
        self.assertTrue(len(result["recommendations"]) > 0)
        self.assertNotIn("jio_101", [r["song_id"] for r in result["recommendations"]])
        self.assertEqual(result["model_version"], self.content_service.model_version)

    def test_popular_fallback_when_seed_unknown(self):
        from unittest.mock import MagicMock
        from app.services.recommendation_service import get_recommendations
        from app.services.cf_engine import cf_engine

        mock_db = MagicMock()
        mock_interaction = MagicMock()
        mock_interaction.user_id = "user_99"
        mock_interaction.song_id = "unknown_song_id"
        mock_interaction.interaction_type = "like"

        mock_query = mock_db.query.return_value.filter.return_value.order_by.return_value
        mock_query.all.return_value = [mock_interaction]

        cf_engine._is_trained = False
        # Mock popular songs fallback
        cf_engine.get_popular_songs = MagicMock(return_value=[{"song_id": "pop_1", "score": 4.0, "rank": 1}])

        result = get_recommendations(user_id="user_99", db=mock_db, n=3)

    def test_skip_ignored_and_earlier_positive_chosen_as_seed(self):
        from unittest.mock import MagicMock
        from app.services.recommendation_service import get_recommendations
        from app.services.cf_engine import cf_engine

        mock_db = MagicMock()
        # Most recent interaction is a SKIP on jio_102
        skip_interaction = MagicMock()
        skip_interaction.user_id = "user_skip"
        skip_interaction.song_id = "jio_102"
        skip_interaction.interaction_type = "skip"

        # Earlier interaction is a LIKE on jio_101
        like_interaction = MagicMock()
        like_interaction.user_id = "user_skip"
        like_interaction.song_id = "jio_101"
        like_interaction.interaction_type = "like"

        mock_query = mock_db.query.return_value.filter.return_value.order_by.return_value
        mock_query.all.return_value = [skip_interaction, like_interaction]

        cf_engine._is_trained = False

        result = get_recommendations(user_id="user_skip", db=mock_db, n=3)

        # Confirm content_based was used with jio_101 as seed
        self.assertEqual(result["source"], "content_based")
        rec_ids = [r["song_id"] for r in result["recommendations"]]
        # Both the seed (jio_101) AND the skipped song (jio_102) must be excluded from recs!
        self.assertNotIn("jio_101", rec_ids)
        self.assertNotIn("jio_102", rec_ids)

    def test_only_skips_falls_through_to_popular(self):
        from unittest.mock import MagicMock
        from app.services.recommendation_service import get_recommendations
        from app.services.cf_engine import cf_engine

        mock_db = MagicMock()
        # User ONLY has skip and unlike interactions
        skip_interaction = MagicMock()
        skip_interaction.user_id = "user_negative_only"
        skip_interaction.song_id = "jio_101"
        skip_interaction.interaction_type = "skip"

        unlike_interaction = MagicMock()
        unlike_interaction.user_id = "user_negative_only"
        unlike_interaction.song_id = "jio_102"
        unlike_interaction.interaction_type = "unlike"

        mock_query = mock_db.query.return_value.filter.return_value.order_by.return_value
        mock_query.all.return_value = [skip_interaction, unlike_interaction]

        cf_engine._is_trained = False
        cf_engine.get_popular_songs = MagicMock(return_value=[{"song_id": "pop_1", "score": 4.0, "rank": 1}])

        result = get_recommendations(user_id="user_negative_only", db=mock_db, n=3)

        # Must fall through to Tier 3 (popular) instead of using skipped song as seed
        self.assertEqual(result["source"], "popular")
        self.assertEqual(result["recommendations"][0]["song_id"], "pop_1")


if __name__ == "__main__":
    unittest.main()


