"""
Song Embedding ORM Model — pgvector storage for content-based filtering.

Stores a 384-dim sentence-transformers vector per song alongside basic
metadata for display in semantic search results.

The HNSW index on the vector column enables sub-millisecond approximate
nearest-neighbour (ANN) search across millions of songs.
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, String, BigInteger, DateTime
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

    title = Column(String(512), nullable=False)
    artist_name = Column(String(255), nullable=True)

    # 384-dimensional embedding from all-MiniLM-L6-v2
    # HNSW index created separately (see database.py ensure_pgvector_extension)
    embedding = Column(Vector(384), nullable=True)

    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<SongEmbedding song_id={self.song_id!r} title={self.title!r}>"
