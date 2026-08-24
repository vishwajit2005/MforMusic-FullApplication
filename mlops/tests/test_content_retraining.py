"""
Unit & Integration Tests for Content-Based Model Organic Growth & Retraining

Tests:
1. Acoustic feature extraction (63 features schema and calculations).
2. Queue feature extraction endpoint (POST /api/v1/content/queue-feature-extraction).
3. Hot-swap retraining logic with synthetic audio feature rows (POST /api/v1/content/model/retrain).
4. Content model status endpoint (GET /api/v1/content/model/status).
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.song_audio_feature import SongAudioFeature, FEATURE_COLUMNS_63
from app.services.audio_feature_extractor import extract_features_from_audio_array
from app.services.content_recommendation_service import ContentRecommendationService


class TestContentOrganicGrowthAndRetraining(unittest.TestCase):

    def setUp(self):
        # Create in-memory SQLite DB for testing
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

        self.db = self.TestingSessionLocal()

        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

        from app.services.content_recommendation_service import content_service
        content_service.load_artifacts("app/data/content_model")

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        app.dependency_overrides.clear()

    def test_extract_features_schema_63_columns(self):
        """Verify audio feature extractor computes all 63 expected feature keys."""
        # Generate synthetic mono audio signal (1 second of 440Hz sine wave)
        sr = 22050
        t = np.linspace(0, 1.0, sr, endpoint=False)
        y = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

        features = extract_features_from_audio_array(y, sr)
        self.assertEqual(len(features), 63)
        for col in FEATURE_COLUMNS_63:
            self.assertIn(col, features)
            self.assertIsInstance(features[col], float)

    def test_queue_feature_extraction_endpoint(self):
        """Test POST /api/v1/content/queue-feature-extraction returns 202 Accepted."""
        payload = {
            "song_id": "test_track_123",
            "audio_url": "https://example.com/audio.mp3",
            "title": "Test Song",
            "artist_name": "Test Artist",
            "album": "Test Album",
            "language": "hindi",
            "decade": "2020s",
        }
        response = self.client.post("/api/v1/content/queue-feature-extraction", json=payload)
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["status"], "queued")
        self.assertEqual(data["song_id"], "test_track_123")

    def test_content_model_status_endpoint(self):
        """Test GET /api/v1/content/model/status returns correct structure."""
        # Insert a pending un-incorporated row
        row = SongAudioFeature(
            song_id="pending_song_1",
            title="Pending Track",
            artist_name="Artist",
            language="hindi",
            decade="2020s",
            incorporated_in_model=False,
            **{col: 0.5 for col in FEATURE_COLUMNS_63},
        )
        self.db.add(row)
        self.db.commit()

        response = self.client.get("/api/v1/content/model/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ready"])
        self.assertFalse(data["retraining"])
        self.assertGreaterEqual(data["total_tracks"], 0)
        self.assertEqual(data["unincorporated_tracks"], 1)

    def test_content_service_retrain_and_hot_swap(self):
        """Test retraining merges new tracks, refits NN, updates DB flag, and updates in-memory version."""
        temp_dir = tempfile.mkdtemp()
        try:
            # Copy existing model artifacts to temp directory
            src_dir = "app/data/content_model"
            if os.path.exists(src_dir):
                for fname in os.listdir(src_dir):
                    s_path = os.path.join(src_dir, fname)
                    if os.path.isfile(s_path):
                        shutil.copy(s_path, os.path.join(temp_dir, fname))

            service = ContentRecommendationService()
            loaded = service.load_artifacts(temp_dir)
            self.assertTrue(loaded)
            initial_count = service.total_tracks

            # Add synthetic new audio feature row to DB
            new_id = "synthetic_track_999"
            row = SongAudioFeature(
                song_id=new_id,
                title="Synthetic New Song",
                artist_name="Synthetic Artist",
                album="Synthetic Album",
                language="punjabi",
                decade="2020s",
                incorporated_in_model=False,
                **{col: 0.25 for col in FEATURE_COLUMNS_63},
            )
            self.db.add(row)
            self.db.commit()

            # Retrain with force=True using temp dir
            with patch("app.services.content_recommendation_service.get_settings") as mock_settings:
                mock_settings.return_value.CONTENT_MODEL_DIR = temp_dir
                mock_settings.return_value.MIN_NEW_SONGS_FOR_CONTENT_RETRAIN = 20

                success = service.train(self.db, force=True)
                self.assertTrue(success)

            # Check track count incremented
            self.assertEqual(service.total_tracks, initial_count + 1)
            self.assertTrue(service.has_track(new_id))
            meta = service.get_track_metadata(new_id)
            self.assertIsNotNone(meta)
            self.assertEqual(meta["title"], "Synthetic New Song")

            # Check DB row is marked incorporated
            db_row = self.db.query(SongAudioFeature).filter(SongAudioFeature.song_id == new_id).first()
            self.assertTrue(db_row.incorporated_in_model)

        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()
