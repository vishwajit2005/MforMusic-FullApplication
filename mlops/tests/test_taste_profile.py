"""Query-side regressions. Fitted synthetic models below are test fixtures only."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import numpy as np
from sklearn.neighbors import NearestNeighbors
from app.services.content_recommendation_service import ContentRecommendationService
from app.services import recommendation_service as routing
from app.schemas.recommendation import RecommendationResponse


def make_service():
    s = ContentRecommendationService()
    ids = ['mellow', 'energetic', 'mellow_new', 'energetic_new', 'blend', 'skip', 'unlike']
    s._features_matrix = np.array([[1, 0], [0, 1], [.99, .01], [.01, .99], [.5, .5], [.6, .4], [.4, .6]], dtype=np.float32)
    s._nn_model = NearestNeighbors(metric='cosine').fit(s._features_matrix)
    s._track_ids = ids
    s._track_id_to_idx = {tid: i for i, tid in enumerate(ids)}
    s._idx_to_track_id = dict(enumerate(ids))
    s._is_ready = True
    s._model_version = 'fixture_7'
    return s


class TestTasteVector(unittest.TestCase):
    def setUp(self):
        self.service = make_service()

    def test_mixed_profile_uses_both_songs_without_fit(self):
        with patch.object(self.service._nn_model, 'fit', side_effect=AssertionError('must not refit')):
            before = self.service.get_similar_songs('mellow', exclude_ids={'energetic', 'skip', 'unlike'})
            after = self.service.get_taste_recommendations(['mellow', 'energetic'], exclude_ids={'skip', 'unlike'})
        self.assertEqual(before[0]['song_id'], 'mellow_new')
        self.assertEqual(after[0]['song_id'], 'blend')
        self.assertEqual([r['rank'] for r in after], list(range(1, len(after) + 1)))
        self.assertEqual([r['score'] for r in after], sorted([r['score'] for r in after], reverse=True))
        self.assertFalse({'mellow', 'energetic', 'skip', 'unlike'} & {r['song_id'] for r in after})

    def test_missing_tracks_keep_original_weights(self):
        model = self.service._nn_model
        with patch.object(model, 'kneighbors', wraps=model.kneighbors) as query:
            self.service.get_taste_recommendations(['missing', 'mellow', 'missing2', 'energetic'])
        np.testing.assert_allclose(query.call_args.args[0], [[9 / 16, 7 / 16]])

    def test_one_known_track_preserves_single_seed_result(self):
        self.assertEqual(self.service.get_taste_recommendations(['missing', 'mellow', 'missing2']), self.service.get_similar_songs('mellow'))

    def test_interest_shifts_gradually(self):
        shares = []
        for count in range(11):
            model = self.service._nn_model
            with patch.object(model, 'kneighbors', wraps=model.kneighbors) as query:
                self.service.get_taste_recommendations(['energetic'] * count + ['mellow'] * (10 - count))
            shares.append(float(query.call_args.args[0][0, 1]))
        self.assertEqual(shares[0], 0)
        self.assertAlmostEqual(shares[1], 10 / 55)
        self.assertEqual(shares[-1], 1)
        self.assertTrue(all(a < b for a, b in zip(shares, shares[1:])))

    def test_window_is_ten_events_not_ten_catalog_matches(self):
        self.assertEqual(self.service.get_taste_recommendations(['missing'] * 10 + ['mellow']), [])

    def test_empty_unknown_exhausted_and_unready(self):
        for ids in ([], ['missing']):
            self.assertEqual(self.service.get_taste_recommendations(ids), [])
        self.assertEqual(self.service.get_taste_recommendations(['mellow'], exclude_ids=self.service._track_ids), [])
        self.assertEqual(ContentRecommendationService().get_taste_recommendations(['mellow']), [])
        self.assertEqual(self.service.get_taste_recommendations(['mellow'], n=0), [])

    def test_failure_is_empty_and_artifacts_unchanged(self):
        original = self.service._features_matrix.copy()
        with patch.object(self.service._nn_model, 'kneighbors', side_effect=RuntimeError('test failure')):
            self.assertEqual(self.service.get_taste_recommendations(['mellow']), [])
        np.testing.assert_array_equal(self.service._features_matrix, original)
        self.assertEqual(self.service.model_version, 'fixture_7')


class TestTasteRouting(unittest.TestCase):
    def setUp(self):
        self.service = make_service()
        self.cf = MagicMock(is_trained=False, model_version='untrained')
        self.cf.get_popular_songs.return_value = [{'song_id': 'popular', 'rank': 1, 'score': 1.0}]
        self.db = MagicMock()
        for name, obj in [('content_service', self.service), ('cf_engine', self.cf)]:
            p = patch.object(routing, name, obj)
            p.start()
            self.addCleanup(p.stop)

    def history(self, rows):
        self.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [SimpleNamespace(song_id=s, interaction_type=k) for s, k in rows]

    def test_negative_events_never_seed_all_history_excluded(self):
        self.history([('skip', 'skip'), ('unlike', 'unlike'), ('missing', 'like'), ('mellow', 'play'), ('energetic', 'download'), ('mellow', 'playlist_add'), ('blend', 'unknown')])
        with patch.object(self.service, 'get_taste_recommendations', wraps=self.service.get_taste_recommendations) as query:
            result = routing.get_recommendations('1', self.db, 3)
        self.assertEqual(query.call_args.kwargs['recent_positive_track_ids'], ['missing', 'mellow', 'energetic', 'mellow'])
        self.assertEqual(query.call_args.kwargs['exclude_ids'], {'skip', 'unlike', 'missing', 'mellow', 'energetic', 'blend'})
        self.assertEqual(result['source'], 'content_based')
        self.assertEqual(result['model_version'], 'fixture_7')
        self.assertEqual(result['total'], len(result['recommendations']))
        RecommendationResponse(**result)
        self.cf.get_popular_songs.assert_not_called()

    def test_latest_ten_positive_window(self):
        self.history([('skip', 'skip')] + [('missing', 'like')] * 10 + [('mellow', 'like')])
        with patch.object(self.service, 'get_taste_recommendations', wraps=self.service.get_taste_recommendations) as query:
            result = routing.get_recommendations('1', self.db)
        self.assertEqual(len(query.call_args.kwargs['recent_positive_track_ids']), 10)
        self.assertEqual(result['source'], 'popular')
        self.assertIn('mellow', query.call_args.kwargs['exclude_ids'])

    def test_negative_only_and_no_history_fallback(self):
        for history in ([], [('skip', 'skip'), ('unlike', 'unlike')]):
            self.history(history)
            with patch.object(self.service, 'get_taste_recommendations', wraps=self.service.get_taste_recommendations) as query:
                self.assertEqual(routing.get_recommendations('1', self.db)['source'], 'popular')
                query.assert_not_called()
        self.cf.get_popular_songs.return_value = []
        self.assertEqual(routing.get_recommendations('1', self.db)['source'], 'cold_start')

    @patch.object(routing.settings, "RECOMMENDATION_PRIORITY", "cf_first")
    def test_cf_keeps_priority_and_empty_cf_falls_through(self):
        self.history([('mellow', 'like')] * routing.settings.MIN_INTERACTIONS_FOR_CF)
        self.cf.is_trained = True
        self.cf.recommend_for_user.return_value = [{'song_id': 'cf_song', 'rank': 1, 'score': .8}]
        with patch.object(self.service, 'get_taste_recommendations', wraps=self.service.get_taste_recommendations) as query:
            self.assertEqual(routing.get_recommendations('1', self.db)['source'], 'collaborative_filtering')
            query.assert_not_called()
        self.cf.recommend_for_user.return_value = []
        self.assertEqual(routing.get_recommendations('1', self.db)['source'], 'content_based')

    def test_http_response_keeps_contract(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.v1.recommendations import router
        from app.core.database import get_db
        self.history([('mellow', 'like'), ('energetic', 'play')])
        app = FastAPI()
        app.include_router(router, prefix='/api/v1/recommendations')
        app.dependency_overrides[get_db] = lambda: self.db
        response = TestClient(app).get('/api/v1/recommendations/1?n=3')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {'user_id', 'recommendations', 'model_version', 'total', 'source'})
        self.assertEqual(body['source'], 'content_based')
        self.assertEqual(body['model_version'], 'fixture_7')
        self.assertFalse({'mellow', 'energetic'} & {r['song_id'] for r in body['recommendations']})


if __name__ == '__main__':
    unittest.main()
