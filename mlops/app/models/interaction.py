from sqlalchemy import Column, String, Integer, Float, BigInteger, DateTime, Index
from sqlalchemy.sql import func
from app.core.database import Base


class Interaction(Base):
    """
    Mirrors the telemetry events forwarded by the Spring Boot backend.
    Stored in PostgreSQL for ML training (separate from MySQL user_interactions).
    This table is the training data source for the ALS collaborative filter.
    """
    __tablename__ = "interactions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # user_id: String to stay UUID-ready (Spring Boot sends Long.toString())
    user_id = Column(String(64), nullable=False)

    # song_id: JioSaavn externalTrackId — the canonical song identifier
    song_id = Column(String(255), nullable=False)

    # Interaction type: play | skip | like | unlike | download | playlist_add
    interaction_type = Column(String(32), nullable=False)

    # Playback telemetry — used for scoring in the CF weight matrix
    play_duration_sec = Column(Integer, default=0)
    completion_rate = Column(Float, default=0.0)

    # Session context
    session_id = Column(String(64), nullable=True)

    # Device epoch timestamp (ms) — preserved for temporal analysis
    device_timestamp = Column(BigInteger, nullable=True)

    # Server ingestion timestamp
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_interactions_user_id", "user_id"),
        Index("idx_interactions_song_id", "song_id"),
        Index("idx_interactions_created_at", "created_at"),
        Index("idx_interactions_user_song", "user_id", "song_id"),
    )

    def __repr__(self):
        return (
            f"<Interaction id={self.id} user={self.user_id} "
            f"song={self.song_id} type={self.interaction_type}>"
        )
