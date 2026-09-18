import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_taste_profile import make_service
from app.api.v1 import recommendations as api
from app.services import recommendation_service as routing
from app.services.recommendation_metrics import RecommendationMetrics
from app.core.database import get_db


class TestNowPlayingVector(unittest.TestCase):
    def setUp(self):
        self.service = make_service()

    def test_current_outweighs_four_context_events_same_model_no_fit(self):
        model = self.service._nn_model
        with patch.object(model, 'fit', side_effect=AssertionError('no refit')), patch.object(model, 'kneighbors', wraps=model.kneighbors) as query:
            recs = self.service.get_now_playing_recommendations('energetic', ['mellow'] * 4, exclude_ids={'skip', 'unlike'})
        np.testing.assert_allclose(query.call_args.args[0], [[24/94, 70/94]])
        self.assertIs(self.service._nn_model, model)
        self.assertFalse({'energetic', 'mellow', 'skip', 'unlike'} & {r['song_id'] for r in recs})
        self.assertEqual([r['rank'] for r in recs], list(range(1, len(recs) + 1)))

    def test_unknown_current_uses_context_weights(self):
        model = self.service._nn_model
        with patch.object(model, 'kneighbors', wraps=model.kneighbors) as query:
            recs = self.service.get_now_playing_recommendations('unknown', ['mellow', 'energetic'])
        np.testing.assert_allclose(query.call_args.args[0], [[.6, .4]])
        self.assertTrue(recs)
        self.assertFalse({'mellow', 'energetic'} & {r['song_id'] for r in recs})

    def test_unknown_context_is_skipped_without_changing_positions(self):
        model = self.service._nn_model
        with patch.object(model, 'kneighbors', wraps=model.kneighbors) as query:
            self.service.get_now_playing_recommendations('unknown', ['mellow', 'unknown2', 'energetic'])
        np.testing.assert_allclose(query.call_args.args[0], [[12/18, 6/18]])

    def test_current_only_matches_existing_song_similarity(self):
        self.assertEqual(self.service.get_now_playing_recommendations('mellow', []), self.service.get_similar_songs('mellow'))

    def test_unknown_unready_exhausted_and_failed_queries_are_empty(self):
        self.assertEqual(self.service.get_now_playing_recommendations('unknown', ['missing']), [])
        self.assertEqual(self.service.get_now_playing_recommendations('mellow', [], exclude_ids=self.service._track_ids), [])
        with patch.object(self.service._nn_model, 'kneighbors', side_effect=RuntimeError('test failure')):
            self.assertEqual(self.service.get_now_playing_recommendations('mellow', []), [])
        self.service._is_ready = False
        self.assertEqual(self.service.get_now_playing_recommendations('mellow', []), [])

    def test_distinct_from_broad_taste_and_context_limited_to_four(self):
        model = self.service._nn_model
        with patch.object(model, 'kneighbors', wraps=model.kneighbors) as query:
            self.service.get_taste_recommendations(['energetic'] + ['mellow'] * 9)
            broad = query.call_args.args[0].copy()
            self.service.get_now_playing_recommendations('energetic', ['mellow'] * 4 + ['energetic'])
            immediate = query.call_args.args[0].copy()
        np.testing.assert_allclose(broad, [[45/55, 10/55]])
        np.testing.assert_allclose(immediate, [[24/94, 70/94]])


class TestSimilarEndpoint(unittest.TestCase):
    def setUp(self):
        self.service = make_service()
        self.db = MagicMock()
        self.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            SimpleNamespace(song_id=song, interaction_type='play', completion_rate=1.0)
            for song in ['skip', 'unlike', 'blend']
        ]
        self.cf = MagicMock()
        self.metrics = RecommendationMetrics()
        for obj, name, value in [(routing, 'content_service', self.service), (routing, 'cf_engine', self.cf), (api, 'recommendation_metrics', self.metrics)]:
            p = patch.object(obj, name, value);p.start();self.addCleanup(p.stop)
        self.app = FastAPI()
        self.app.include_router(api.router, prefix='/api/v1/recommendations')
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)
        self.url = '/api/v1/recommendations/similar'

    def test_static_route_response_exclusions_and_separate_metrics(self):
        response = self.client.get(self.url, params=[('user_id', '1'), ('current_song_id', 'energetic'), ('context_song_ids', 'mellow'), ('n', '2')])
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['user_id'], '1')
        self.assertEqual(body['current_song_id'], 'energetic')
        self.assertEqual(body['source'], 'content_based')
        self.assertEqual(body['model_version'], 'fixture_7')
        self.assertEqual(body['total'], 2)
        self.assertFalse({'energetic', 'mellow', 'skip', 'unlike', 'blend'} & {r['song_id'] for r in body['recommendations']})
        self.assertEqual(self.metrics.snapshot()['observed_requests'], 0)
        self.cf.recommend_for_user.assert_not_called()
        self.cf.get_popular_songs.assert_not_called()

    def test_missing_current_uses_context_or_empty_never_popular(self):
        for context, expected_empty in [(['mellow'], False), (['unknown2'], True), ([], True)]:
            with self.subTest(context=context):
                params=[('user_id', '1'), ('current_song_id', 'unknown')] + [('context_song_ids', s) for s in context]
                r=self.client.get(self.url, params=params)
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json()['recommendations'] == [], expected_empty)
        self.cf.get_popular_songs.assert_not_called()
        self.cf.recommend_for_user.assert_not_called()

    def test_input_validation(self):
        base=[('user_id', '1'), ('current_song_id', 'mellow')]
        for params in [[], base+[('context_song_ids', 'x')]*5, base+[('n', '0')], base+[('n', '51')], [('user_id', '1'), ('current_song_id', ' ')], base+[('context_song_ids', '')]]:
            with self.subTest(params=params):
                self.assertEqual(self.client.get(self.url, params=params).status_code, 422)

    def test_cloud_auth_protects_route(self):
        import os
        from app.deployment.auth import ServiceAuth
        with patch.dict(os.environ, {'MLOPS_API_KEY': 's' * 32}):
            client=TestClient(ServiceAuth(self.app))
        params={'user_id':'1','current_song_id':'mellow'}
        self.assertEqual(client.get(self.url,params=params).status_code,401)
        self.assertEqual(client.get(self.url,params=params,headers={'X-MforMusic-Key':'s'*32}).status_code,200)


if __name__ == '__main__':
    unittest.main()
