import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.v1 import recommendations as api
from app.services import recommendation_service as service
from app.services.recommendation_metrics import RecommendationMetrics
from app.core.database import get_db


class TestWindow(unittest.TestCase):
    def test_empty_window_and_exact_distribution(self):
        m = RecommendationMetrics()
        self.assertEqual(m.snapshot()['observed_requests'], 0)
        self.assertIsNone(m.snapshot()['oldest_request_at'])
        self.assertTrue(all(v['percent'] == 0 for v in m.snapshot()['distribution'].values()))
        for source, n in [('content_based', 70), ('collaborative_filtering', 5), ('popular', 25)]:
            for _ in range(n):
                m.record(source, 'content_first', 'no_recent_catalog_match' if source == 'popular' else None)
        s = m.snapshot()
        self.assertEqual(s['observed_requests'], 100)
        self.assertEqual(s['distribution']['content_based'], {'count': 70, 'percent': 70.0})
        self.assertEqual(s['distribution']['collaborative_filtering']['percent'], 5.0)
        self.assertEqual(s['distribution']['popular']['percent'], 25.0)
        self.assertEqual(s['fallback_reasons'], {'no_recent_catalog_match': 25})
        m.record('cold_start', 'cf_first', 'no_history')
        m.record('error', 'cf_first')
        s = m.snapshot()
        self.assertEqual(s['observed_requests'], 100)
        self.assertEqual(s['distribution']['content_based']['count'], 68)
        self.assertEqual(s['distribution']['cold_start']['count'], 1)
        self.assertEqual(s['distribution']['error']['count'], 1)
        self.assertEqual(s['priority_counts'], {'content_first': 98, 'cf_first': 2})

    def test_concurrent_writes_stay_bounded_and_new_instance_is_empty(self):
        m = RecommendationMetrics()
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: m.record('content_based', 'content_first'), range(1000)))
        self.assertEqual(m.snapshot()['observed_requests'], 100)
        self.assertEqual(m.snapshot()['distribution']['content_based']['percent'], 100.0)
        self.assertEqual(RecommendationMetrics().snapshot()['observed_requests'], 0)


class TestMetricsEndpoint(unittest.TestCase):
    def setUp(self):
        self.metrics = RecommendationMetrics()
        self.db = MagicMock()
        app = FastAPI()
        app.include_router(api.router, prefix='/api/v1/recommendations')
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app, raise_server_exceptions=False)
        p = patch.object(api, 'recommendation_metrics', self.metrics)
        p.start()
        self.addCleanup(p.stop)

    def test_each_response_counted_once_reads_not_counted(self):
        for source in ('content_based', 'collaborative_filtering', 'popular', 'cold_start'):
            result = {'user_id': '1', 'recommendations': [], 'model_version': 'v', 'total': 0, 'source': source}
            with patch.object(api, 'get_recommendations', return_value=result):
                r = self.client.get('/api/v1/recommendations/1')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json(), result)
        for _ in range(2):
            r = self.client.get('/api/v1/recommendations/metrics/distribution')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()['observed_requests'], 4)
        self.assertEqual(r.json()['distribution']['popular']['percent'], 25)

    def test_handler_errors_separate_from_validation_rejections(self):
        with patch.object(api, 'get_recommendations', side_effect=RuntimeError('test failure')):
            self.assertEqual(self.client.get('/api/v1/recommendations/1').status_code, 500)
        self.assertEqual(self.client.get('/api/v1/recommendations/1?n=0').status_code, 422)
        self.assertEqual(self.metrics.snapshot()['observed_requests'], 1)
        self.assertEqual(self.metrics.snapshot()['distribution']['error']['count'], 1)

    def test_fallback_reasons_distinguish_coverage_from_other_causes(self):
        cases = [
            (True, [], False, 'no_history'),
            (True, ['skip'], False, 'no_positive_history'),
            (False, ['like'], False, 'content_model_unavailable'),
            (True, ['like'], False, 'no_recent_catalog_match'),
            (True, ['like'], True, 'no_content_results'),
        ]
        for ready, kinds, matched, reason in cases:
            with self.subTest(reason=reason):
                content = MagicMock(is_ready=ready, model_version='content_v')
                content.get_taste_recommendations.return_value = []
                content.has_track.return_value = matched
                cf = MagicMock(is_trained=False, model_version='untrained')
                cf.get_popular_songs.return_value = [{'song_id': 'pop', 'rank': 1, 'score': 1}]
                self.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [SimpleNamespace(song_id='seed', interaction_type=k) for k in kinds]
                with patch.object(service, 'content_service', content), patch.object(service, 'cf_engine', cf):
                    r = self.client.get('/api/v1/recommendations/1')
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json()['source'], 'popular')
                self.assertEqual(self.metrics.snapshot()['fallback_reasons'][reason], 1)
                self.assertNotIn('content_fallback_reason', r.json())

    def test_cloud_auth_still_protects_metrics(self):
        from app.deployment.auth import ServiceAuth
        import os
        app = FastAPI()
        app.include_router(api.router, prefix='/api/v1/recommendations')
        with patch.dict(os.environ, {'MLOPS_API_KEY': 't' * 32}):
            client = TestClient(ServiceAuth(app))
        url = '/api/v1/recommendations/metrics/distribution'
        self.assertEqual(client.get(url).status_code, 401)
        self.assertEqual(client.get(url, headers={'X-MforMusic-Key': 't' * 32}).status_code, 200)
        self.assertEqual(self.metrics.snapshot()['observed_requests'], 0)


if __name__ == '__main__':
    unittest.main()
