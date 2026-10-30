"""Version de-duplication and title+artist embedding fallback (post-processing only)."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd

from app.services import recommendation_service as routing
from app.services.version_dedup import artist_set, collapse_versions, core_title
from test_taste_profile import make_service


def recs(*ids):
    return [{"song_id": s, "score": 1 - i / 100, "rank": i + 1} for i, s in enumerate(ids)]


class TestCoreTitle(unittest.TestCase):
    def test_release_markers_are_stripped(self):
        for title in ['Tum Hi Ho (From "Aashiqui 2")', 'Tum Hi Ho', 'Tum Hi Ho (From &quot;Aashiqui 2&quot;)',
                      'Tum Hi Ho - Flute Instrumental', 'TUM HI HO [Lofi]', 'Tum Hi Ho feat. Someone']:
            self.assertEqual(core_title(title), 'tum hi ho', title)

    def test_artist_order_and_separators(self):
        self.assertEqual(artist_set('Mithoon, Arijit Singh'), artist_set('Arijit Singh & Mithoon'))
        self.assertEqual(artist_set('Unknown Artist'), frozenset())


class TestCollapseVersions(unittest.TestCase):
    META = {
        'a': ('Tum Hi Ho (From "Aashiqui 2")', 'Mithoon, Arijit Singh'),
        'b': ('Tum Hi Ho', 'Arijit Singh, Mithoon'),
        'c': ('Tum Hi Ho - Flute Instrumental', 'Mithoon'),
        'd': ('Tum Hi Ho', 'Some Other Band'),      # same name, different song
        'e': ('Kya Karoon?', 'Zaeden'),
        'f': ('5 am', 'Zaeden'),
        'g': ('5 am', 'Zaeden'),
    }

    def test_keeps_best_ranked_version_only(self):
        out = collapse_versions(recs('a', 'b', 'c', 'd', 'e', 'f', 'g'), self.META, 10)
        self.assertEqual([r['song_id'] for r in out], ['a', 'd', 'e', 'f'])
        self.assertEqual([r['rank'] for r in out], [1, 2, 3, 4])

    def test_blocked_songs_block_their_versions_and_fill_to_n(self):
        out = collapse_versions(recs('b', 'c', 'e', 'f', 'x'), self.META, 2, blocked_song_ids=['a'])
        self.assertEqual([r['song_id'] for r in out], ['e', 'f'])

    def test_unknown_metadata_is_kept_and_scores_untouched(self):
        original = recs('x', 'a', 'y', 'b')
        out = collapse_versions(original, self.META, 10)
        self.assertEqual([r['song_id'] for r in out], ['x', 'a', 'y'])
        self.assertEqual([r['score'] for r in out], [original[0]['score'], original[1]['score'], original[2]['score']])

    def test_real_catalog_duplicates_collapse(self):
        index = pd.read_csv(Path(__file__).resolve().parent.parent / 'app/data/content_model/track_index.csv')
        meta = {str(r.external_track_id): (r.title, r.artist) for r in index.itertuples()}
        ids = [sid for sid, (t, _) in meta.items() if core_title(t) == 'tum hi ho']
        self.assertGreaterEqual(len(ids), 3)
        self.assertEqual(len(collapse_versions(recs(*ids), meta, 10)), 1)


class TestForYouPostProcessing(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            SimpleNamespace(song_id='heard', interaction_type='PLAY', completion_rate=1.0)]
        self.content = MagicMock(is_ready=True, model_version='cv')
        self.content.has_track.return_value = True
        meta = {'heard': {'title': 'Tum Hi Ho', 'artist': 'Arijit Singh'},
                'v1': {'title': 'Tum Hi Ho (From "Aashiqui 2")', 'artist': 'Arijit Singh, Mithoon'},
                'k1': {'title': 'Kesariya', 'artist': 'Arijit Singh'},
                'k2': {'title': 'Kesariya - Lofi', 'artist': 'Arijit Singh'},
                'z1': {'title': 'Raaz', 'artist': 'Zaeden'}}
        self.content.get_track_metadata.side_effect = meta.get
        self.content.get_taste_recommendations.return_value = recs('v1', 'k1', 'k2', 'z1')
        self.cf = MagicMock(is_trained=False)
        for name, value in [('content_service', self.content), ('cf_engine', self.cf)]:
            p = patch.object(routing, name, value); p.start(); self.addCleanup(p.stop)
        p = patch.object(routing.settings, 'RECOMMENDATION_PRIORITY', 'content_first'); p.start(); self.addCleanup(p.stop)

    def test_versions_of_heard_and_duplicate_versions_are_removed(self):
        out = routing.get_recommendations('1', self.db, n=5)
        self.assertEqual(out['source'], 'content_based')
        self.assertEqual([r['song_id'] for r in out['recommendations']], ['k1', 'z1'])
        # Over-fetch so de-duplication can still fill the requested count.
        self.assertGreater(self.content.get_taste_recommendations.call_args.kwargs['n'], 5)

    def test_unknown_seed_gets_embedding_share(self):
        self.content.has_track.return_value = False
        with patch.object(routing.embedding_recommender, 'taste_recommendations', return_value=recs('e1', 'e2')) as emb:
            out = routing.get_recommendations('1', self.db, n=4)
        ids = [r['song_id'] for r in out['recommendations']]
        self.assertIn('e1', ids)
        emb.assert_called()

    def test_embedding_tier_before_popular_when_content_empty(self):
        self.content.get_taste_recommendations.return_value = []
        with patch.object(routing.embedding_recommender, 'taste_recommendations', return_value=recs('e1')):
            out = routing.get_recommendations('1', self.db, n=4)
        self.assertEqual(out['source'], 'embedding_based')
        self.cf.get_popular_songs.assert_not_called()

    def test_embedding_failure_falls_through_to_popular(self):
        self.content.get_taste_recommendations.return_value = []
        self.cf.get_popular_songs.return_value = recs('p1')
        with patch.object(routing.embedding_recommender, 'taste_recommendations', return_value=[]):
            out = routing.get_recommendations('1', self.db, n=4)
        self.assertEqual(out['source'], 'popular')


class TestSimilarFallback(unittest.TestCase):
    def setUp(self):
        self.service = make_service()
        self.db = MagicMock()
        self.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        p = patch.object(routing, 'content_service', self.service); p.start(); self.addCleanup(p.stop)

    def test_unknown_current_song_leads_with_embeddings(self):
        with patch.object(routing.embedding_recommender, 'similar_to_song', return_value=recs('e1', 'e2')) as emb:
            out = routing.get_similar_recommendations('1', 'outside', ['mellow'], self.db, n=3,
                                                      current_song_title='Tum Ho', current_song_artist='Jokhim')
        self.assertEqual(out['source'], 'embedding_based')
        self.assertEqual([r['song_id'] for r in out['recommendations']][:2], ['e1', 'e2'])
        self.assertEqual(len(out['recommendations']), 3)
        self.assertEqual(emb.call_args.kwargs['title'], 'Tum Ho')
        self.assertIn('mellow', emb.call_args.kwargs['exclude_ids'])

    def test_known_current_song_never_calls_embeddings(self):
        with patch.object(routing.embedding_recommender, 'similar_to_song') as emb:
            out = routing.get_similar_recommendations('1', 'energetic', [], self.db, n=2)
        emb.assert_not_called()
        self.assertEqual(out['source'], 'content_based')

    def test_unknown_current_without_embedding_keeps_old_behaviour(self):
        with patch.object(routing.embedding_recommender, 'similar_to_song', return_value=[]):
            out = routing.get_similar_recommendations('1', 'outside', ['mellow'], self.db, n=2)
        self.assertEqual(out['source'], 'content_based')
        self.assertTrue(out['recommendations'])


if __name__ == '__main__':
    unittest.main()
