"""
Song Embedding ORM Model — pgvector storage for content-based filtering.

Stores a 384-dim sentence-transformers vector per song alongside basic
metadata for display in semantic search results.

The HNSW index on the vector column enables sub-millisecond approximate
nearest-neighbour (ANN) search across millions of songs.
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, String, BigInteger, DateTime, Index
from sqlalchemy.sql import func
from app.core.database import Base


class SongEmbedding(Base):
    """
    One row per unique JioSaavn externalTrackId.
    Updated/inserted whenever a new song passes through the ingestion pipeline.
    """
    __tablename__ = "song_embeddings"

    # JioSaavn externalTrackId — matches Interaction.song_id
    song_id = Column(String(255), primary_key=True)

    title = Column(String(1024), nullable=False)
    artist_name = Column(String(1024), nullable=True)

    # 384-dimensional embedding from all-MiniLM-L6-v2
    embedding = Column(Vector(384), nullable=True)

    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index(
            "idx_song_embeddings_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self):
        return f"<SongEmbedding song_id={self.song_id!r} title={self.title!r}>"
