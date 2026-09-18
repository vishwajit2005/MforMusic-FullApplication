"""Serving order and HTTP source contract; training remains independent."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from pydantic import ValidationError
from app.core.config import Settings
from app.services import recommendation_service as service
from app.schemas.interaction import InteractionIngest


def rec(song):
    return [{'song_id': song, 'rank': 1, 'score': .8}]


class TestPriorityConfig(unittest.TestCase):
    def test_default_environment_override_and_validation(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Settings(_env_file=None).RECOMMENDATION_PRIORITY, 'content_first')
        with patch.dict(os.environ, {'RECOMMENDATION_PRIORITY': 'cf_first'}):
            self.assertEqual(Settings(_env_file=None).RECOMMENDATION_PRIORITY, 'cf_first')
        with patch.dict(os.environ, {'RECOMMENDATION_PRIORITY': 'typo'}):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None)


class TestServingPriority(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [SimpleNamespace(song_id='seed', interaction_type='like')] * 3
        self.content = MagicMock(is_ready=True, model_version='content_version')
        self.cf = MagicMock(is_trained=True, model_version='cf_version')
        self.content.get_taste_recommendations.return_value = rec('content_song')
        self.cf.recommend_for_user.return_value = rec('cf_song')
        self.cf.get_popular_songs.return_value = rec('popular_song')
        self.calls = MagicMock()
        for method, label in [(self.content.get_taste_recommendations, 'content'), (self.cf.recommend_for_user, 'cf'), (self.cf.get_popular_songs, 'popular')]:
            self.calls.attach_mock(method, label)
        for name, value in [('content_service', self.content), ('cf_engine', self.cf)]:
            p = patch.object(service, name, value)
            p.start()
            self.addCleanup(p.stop)

    def request(self, priority):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.v1.recommendations import router
        from app.core.database import get_db
        app = FastAPI()
        app.include_router(router, prefix='/api/v1/recommendations')
        app.dependency_overrides[get_db] = lambda: self.db
        with patch.object(service.settings, 'RECOMMENDATION_PRIORITY', priority):
            response = TestClient(app).get('/api/v1/recommendations/1?n=5')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['total'], len(body['recommendations']))
        return body

    def test_first_available_tier_wins_in_both_orders(self):
        for priority, source, first, version in [('content_first', 'content_based', 'content', 'content_version'), ('cf_first', 'collaborative_filtering', 'cf', 'cf_version')]:
            with self.subTest(priority=priority):
                self.calls.reset_mock()
                body = self.request(priority)
                self.assertEqual(body['source'], source)
                self.assertEqual(body['model_version'], version)
                self.assertEqual([c[0] for c in self.calls.mock_calls], [first])
                self.cf.trigger_retrain.assert_not_called()

    def test_empty_first_tier_falls_back_in_both_orders(self):
        for priority, source, order in [('content_first', 'collaborative_filtering', ['content', 'cf']), ('cf_first', 'content_based', ['cf', 'content'])]:
            with self.subTest(priority=priority):
                self.calls.reset_mock()
                self.content.get_taste_recommendations.return_value = [] if priority == 'content_first' else rec('content_song')
                self.cf.recommend_for_user.return_value = [] if priority == 'cf_first' else rec('cf_song')
                body = self.request(priority)
                self.assertEqual(body['source'], source)
                self.assertEqual(body['model_version'], 'cf_version' if source == 'collaborative_filtering' else 'content_version')
                self.assertEqual([c[0] for c in self.calls.mock_calls], order)

    def test_popular_and_cold_start_are_last_in_both_orders(self):
        self.content.get_taste_recommendations.return_value = []
        self.cf.recommend_for_user.return_value = []
        for priority, expected in [('content_first', ['content', 'cf', 'popular']), ('cf_first', ['cf', 'content', 'popular'])]:
            for songs, source in [(rec('popular_song'), 'popular'), ([], 'cold_start')]:
                with self.subTest(priority=priority, source=source):
                    self.calls.reset_mock()
                    self.cf.get_popular_songs.return_value = songs
                    self.assertEqual(self.request(priority)['source'], source)
                    self.assertEqual([c[0] for c in self.calls.mock_calls], expected)

    def test_unavailable_models_are_skipped(self):
        self.content.is_ready = False
        self.assertEqual(self.request('content_first')['source'], 'collaborative_filtering')
        self.content.get_taste_recommendations.assert_not_called()
        self.calls.reset_mock()
        self.content.is_ready = True
        self.cf.is_trained = False
        self.assertEqual(self.request('cf_first')['source'], 'content_based')
        self.cf.recommend_for_user.assert_not_called()

    def test_cf_threshold_still_applies(self):
        self.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [SimpleNamespace(song_id='seed', interaction_type='like')]
        for priority in ('cf_first', 'content_first'):
            self.assertEqual(self.request(priority)['source'], 'content_based')
        self.cf.recommend_for_user.assert_not_called()

    def test_ingestion_triggers_cf_training_in_both_orders(self):
        payload = InteractionIngest(user_id='1', song_id='seed', interaction_type='like')
        for priority in ('content_first', 'cf_first'):
            with self.subTest(priority=priority), patch.object(service.settings, 'RECOMMENDATION_PRIORITY', priority), patch.object(service, '_interaction_count', service.settings.RETRAIN_EVERY_N_INTERACTIONS - 1), patch.object(service, '_upsert_song_embedding_async'):
                self.cf.trigger_retrain.reset_mock()
                _, triggered = service.ingest_interaction(self.db, payload)
                self.assertTrue(triggered)
                self.cf.trigger_retrain.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
