"""Confirmed Similar Songs quality and strong-rejection rules."""
import math
import unittest
from types import SimpleNamespace as Event
from unittest.mock import MagicMock, patch
import numpy as np
from test_taste_profile import make_service
from app.services.content_recommendation_service import _context_quality, REJECT_PENALTY, REJECT_SIMILARITY_THRESHOLD
from app.services import recommendation_service as routing


def event(song='mellow', kind='play', completion=None):
    return Event(song_id=song, interaction_type=kind, completion_rate=completion)


class TestContextQuality(unittest.TestCase):
    def test_all_multipliers_and_invalid_completion(self):
        cases = [('like', None, 1.5), ('playlist_add', 0, 1.5), ('download', None, 1.4),
                 ('play', .6, 1.1), ('play', 0, .5), ('play', 1, 1.5),
                 ('play', None, .8), ('play', 'bad', .8), ('play', float('nan'), .8),
                 ('play', float('inf'), .8), ('play', -2, .5), ('play', 2, 1.5)]
        for kind, completion, expected in cases:
            with self.subTest(kind=kind, completion=completion):
                self.assertAlmostEqual(_context_quality(event(kind=kind, completion=completion)), expected)
        self.assertEqual(_context_quality(None), .8)
        self.assertEqual(_context_quality(Event(interaction_type='play')), .8)

    def test_current_weight_and_all_contexts_normalized(self):
        s=make_service()
        history=[event('mellow','like'),event('mellow_new','play',.6),event('energetic_new','play',0),event('blend','download')]
        context=['mellow','mellow_new','energetic_new','blend']
        raw=np.array([70,18,8.8,3,5.6])
        with patch.object(s,'_get_weighted_recommendations',return_value=[]) as query:
            s.get_now_playing_recommendations('energetic', context, interaction_history=history)
        np.testing.assert_allclose(query.call_args.args[1], raw/raw.sum())
        self.assertAlmostEqual(sum(query.call_args.args[1]),1)

    def test_latest_positive_selected_not_latest_negative(self):
        s=make_service()
        history=[event('mellow','skip',.9),event('mellow','unknown',1),event('mellow','play',.6),event('mellow','like')]
        with patch.object(s,'_get_weighted_recommendations',return_value=[]) as query:
            s.get_now_playing_recommendations('energetic',['mellow'],interaction_history=history)
        np.testing.assert_allclose(query.call_args.args[1],np.array([70,13.2])/83.2)

    def test_no_positive_record_and_no_record_default_to_point_eight(self):
        for history in [[],[event('mellow','skip',None),event('mellow','unlike',1)],[event('mellow','unknown',1)]]:
            with self.subTest(history=history):
                s=make_service()
                with patch.object(s,'_get_weighted_recommendations',return_value=[]) as query:
                    s.get_now_playing_recommendations('energetic',['mellow'],interaction_history=history)
                np.testing.assert_allclose(query.call_args.args[1],np.array([70,9.6])/79.6)

    def test_missing_catalog_tracks_removed_before_normalization(self):
        s=make_service()
        with patch.object(s,'_get_weighted_recommendations',return_value=[]) as query:
            s.get_now_playing_recommendations('missing',['unknown','mellow','energetic'],interaction_history=[event('mellow','like'),event('energetic','play',0)])
        np.testing.assert_allclose(query.call_args.args[1],[0,0,12/15,3/15])

    def test_same_neighbor_count_metric_model_and_exclusion(self):
        s=make_service();model=s._nn_model
        with patch.object(model,'kneighbors',wraps=model.kneighbors) as query, patch.object(model,'fit',side_effect=AssertionError('no fit')):
            results=s.get_now_playing_recommendations('energetic',['mellow'],n=2,exclude_ids={'skip'},interaction_history=[event('mellow','like'),event('skip','skip',None)])
        self.assertEqual(query.call_count,1)
        self.assertEqual(query.call_args.kwargs['n_neighbors'],min(2+3+5,len(s._track_ids)))
        self.assertEqual(model.metric,'cosine')
        self.assertIs(s._nn_model,model)
        self.assertFalse({'energetic','mellow','skip'}&{r['song_id'] for r in results})

    def test_history_read_once_for_quality_rejects_and_full_exclusions(self):
        db=MagicMock();history=[event('mellow','like'),event('skip','skip',None),event('unlike','unlike',1)]
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value=history
        content=MagicMock(model_version='v');content.get_now_playing_recommendations.return_value=[]
        with patch.object(routing,'content_service',content),patch.object(routing,'cf_engine') as cf:
            result=routing.get_similar_recommendations('1','energetic',['mellow'],db)
        db.query.assert_called_once()
        db.query.return_value.filter.return_value.order_by.return_value.all.assert_called_once()
        self.assertIs(content.get_now_playing_recommendations.call_args.kwargs['interaction_history'],history)
        self.assertEqual(content.get_now_playing_recommendations.call_args.kwargs['exclude_ids'],{'mellow','skip','unlike'})
        self.assertEqual(result['source'],'content_based')
        cf.get_popular_songs.assert_not_called()
        db.commit.assert_not_called()


class TestRejectReranking(unittest.TestCase):
    def setUp(self):
        self.s=make_service()
        ids=['reject','high','exact','low','opposite','zero','invalid']
        self.s._track_id_to_idx={tid:i for i,tid in enumerate(ids)}
        self.s._features_matrix=np.array([[1,0],[1,0],[.75,math.sqrt(7)/4],[0,1],[-1,0],[0,0],[float('nan'),0]],dtype=float)
        self.original=[{'song_id':'high','score':1.,'rank':1},{'song_id':'exact','score':.9,'rank':2},{'song_id':'low','score':.8,'rank':3}]

    def test_thresholds_formula_sort_and_no_mutation(self):
        before=[dict(r) for r in self.original]
        results=self.s._rerank_strong_rejects(self.original,[event('reject','unlike',1)])
        self.assertEqual(REJECT_SIMILARITY_THRESHOLD,.75)
        self.assertEqual(REJECT_PENALTY,.30)
        self.assertEqual([r['song_id'] for r in results],['exact','low','high'])
        self.assertEqual([r['score'] for r in results],[.9,.8,.7])
        self.assertEqual([r['rank'] for r in results],[1,2,3])
        self.assertEqual(self.original,before)
        self.assertTrue(all(r is not o for r in results for o in self.original))

    def test_ties_preserve_original_relative_order(self):
        original=[{'song_id':'high','score':1.,'rank':1},{'song_id':'low','score':.7,'rank':2}]
        self.assertEqual([r['song_id'] for r in self.s._rerank_strong_rejects(original,[event('reject','unlike')])],['high','low'])
        original.reverse()
        self.assertEqual([r['song_id'] for r in self.s._rerank_strong_rejects(original,[event('reject','unlike')])],['low','high'])

    def test_no_rejects_or_no_catalog_vectors_returns_original(self):
        for history in [[],[event('reject','like')],[event('absent','unlike')]]:
            with self.subTest(history=history),patch('app.services.content_recommendation_service.np.mean',side_effect=AssertionError('centroid must not run')) as mean:
                self.assertIs(self.s._rerank_strong_rejects(self.original,history),self.original)
                mean.assert_not_called()

    def test_zero_and_invalid_centroid_returns_original(self):
        for ids in [['zero'],['invalid'],['reject','opposite']]:
            with self.subTest(ids=ids):
                self.assertIs(self.s._rerank_strong_rejects(self.original,[event(t,'unlike') for t in ids]),self.original)

    def test_exception_mid_penalty_preserves_every_original_score_and_warns(self):
        original=[dict(r) for r in self.original]+[{'song_id':'missing','score':.6,'rank':4}]
        before=[dict(r) for r in original]
        with self.assertLogs('app.services.content_recommendation_service',level='WARNING'):
            results=self.s._rerank_strong_rejects(original,[event('reject','unlike')])
        self.assertIs(results,original)
        self.assertEqual(original,before)

    def test_exception_in_reject_lookup_is_nonfatal(self):
        with self.assertLogs('app.services.content_recommendation_service',level='WARNING'):
            self.assertIs(self.s._rerank_strong_rejects(self.original,[event('reject','skip','invalid')]),self.original)

    def test_skip_boundary_null_missing_and_unlike_any_completion(self):
        cases=[(event('reject','skip',.2),False),(event('reject','skip',.1999),True),(event('reject','skip',None),True),(Event(song_id='reject',interaction_type='skip'),True),(event('reject','unlike',1),True),(event('reject','unlike',None),True),(event('reject','unlike','invalid'),True)]
        for e,penalized in cases:
            with self.subTest(event=e):
                result=self.s._rerank_strong_rejects(self.original,[e])
                high=next(r for r in result if r['song_id']=='high')
                self.assertEqual(high['score'],.7 if penalized else 1.)

    def test_only_newest_five_matching_events_before_catalog_filtering(self):
        history=[event('reject','play',0)]+[event('absent','unlike')]*5+[event('reject','unlike')]
        self.assertIs(self.s._rerank_strong_rejects(self.original,history),self.original)

    def test_centroid_is_unweighted_average(self):
        history=[event('reject','unlike'),event('low','skip',0)]
        module='app.services.content_recommendation_service'
        with patch(module+'.np.mean',wraps=np.mean) as mean:
            self.s._rerank_strong_rejects(self.original,history)
        np.testing.assert_array_equal(mean.call_args.args[0],[[1,0],[0,1]])
        self.assertEqual(mean.call_args.kwargs,{'axis':0})


if __name__=='__main__':
    unittest.main()
