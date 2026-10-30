"""Real PostgreSQL + pgvector checks for the embedding fallback SQL.

Skipped unless TEST_PGVECTOR_URL points at a disposable database with pgvector, e.g.
  TEST_PGVECTOR_URL=postgresql://postgres@localhost:5432/mlops_test pytest tests/test_embedding_recommender_pg.py
"""
import os
import unittest
from unittest.mock import patch

import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

URL = os.environ.get("TEST_PGVECTOR_URL")


def unit(*xs):
    v = np.zeros(384, dtype=np.float32)
    for i, x in enumerate(xs):
        v[i] = x
    return v / np.linalg.norm(v)


@unittest.skipUnless(URL, "TEST_PGVECTOR_URL not set")
class TestEmbeddingRecommenderOnPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.models.song_embedding import SongEmbedding
        cls.engine = create_engine(URL)
        with cls.engine.begin() as c:
            c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            c.execute(text("DROP TABLE IF EXISTS song_embeddings"))
        SongEmbedding.__table__.create(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        from app.services import embedding_recommender as er
        self.er = er
        with self.engine.begin() as c:
            c.execute(text("TRUNCATE song_embeddings"))
        self.db = self.Session()
        self.addCleanup(self.db.close)
        rows = {"anchor": ("Tum Ho", "Jokhim", unit(1, 0)), "near": ("Tum Ho Reprise", "Jokhim", unit(1, .1)),
                "mid": ("Pal", "Arijit Singh", unit(1, 1)), "far": ("Bhangra", "Diljit", unit(0, 1))}
        for sid, (t, a, v) in rows.items():
            self.db.execute(text("INSERT INTO song_embeddings(song_id,title,artist_name,embedding) "
                                 "VALUES (:s,:t,:a,CAST(:v AS vector))"), {"s": sid, "t": t, "a": a, "v": er._vec_literal(v)})
        self.db.commit()

    def test_similar_to_stored_song_orders_and_excludes(self):
        out = self.er.similar_to_song(self.db, "anchor", 5, exclude_ids={"near"})
        self.assertEqual([r["song_id"] for r in out], ["mid", "far"])
        self.assertGreater(out[0]["score"], out[1]["score"])

    def test_on_the_fly_embedding_for_unstored_song(self):
        with patch("app.services.embedding_service.embed_song", return_value=unit(0, 1)):
            out = self.er.similar_to_song(self.db, "new", 2, title="Some Song", artist="X")
        self.assertEqual(out[0]["song_id"], "far")

    def test_taste_and_metadata_and_failure_isolation(self):
        out = self.er.taste_recommendations(self.db, ["anchor", "far"], [10, 1], 4, exclude_ids={"anchor", "far"})
        self.assertEqual(out[0]["song_id"], "near")
        self.assertEqual(self.er.stored_metadata(self.db, ["mid", "nope"]), {"mid": ("Pal", "Arijit Singh")})
        # A failing query must not poison the session for the caller.
        self.assertEqual(self.er.nearest(self.db, np.ones(3, dtype=np.float32), 3), [])
        self.assertEqual(self.db.execute(text("SELECT count(*) FROM song_embeddings")).scalar(), 4)

    def test_seeding_is_idempotent_and_keeps_existing_titles(self):
        catalog = {"anchor": {"title": "IGNORED", "artist": "x"}, "cat1": {"title": "Kesariya", "artist": "Arijit Singh"},
                   "cat2": {"title": "Raaz", "artist": "Zaeden"}}
        fake = lambda texts: np.vstack([unit(0, 0, 1)] * len(texts))
        with patch("app.core.database.SessionLocal", self.Session), \
             patch("app.services.embedding_service.embed_batch", side_effect=fake) as emb:
            self.assertEqual(self.er.seed_catalog_embeddings(catalog, pause_sec=0), 2)
            self.assertEqual(self.er.seed_catalog_embeddings(catalog, pause_sec=0), 0)
        self.assertEqual(emb.call_count, 1)
        title = self.db.execute(text("SELECT title FROM song_embeddings WHERE song_id='anchor'")).scalar()
        self.assertEqual(title, "Tum Ho")


if __name__ == "__main__":
    unittest.main()
