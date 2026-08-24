"""
Song Audio Feature ORM Model

Stores 63 acoustic features extracted via librosa from audio tracks uploaded to Supabase,
along with metadata (language, decade) and an incorporated_in_model flag for automatic retraining.
"""

from sqlalchemy import Column, String, Float, Boolean, DateTime, Index
from sqlalchemy.sql import func
from app.core.database import Base


FEATURE_COLUMNS_63 = [
    "tempo",
    "rms_mean", "rms_std",
    "spectral_centroid_mean", "spectral_centroid_std",
    "spectral_rolloff_mean", "spectral_rolloff_std",
    "spectral_bandwidth_mean", "spectral_bandwidth_std",
    "spectral_flatness_mean", "spectral_flatness_std",
    "zero_crossing_rate_mean", "zero_crossing_rate_std",
    # 13 MFCCs (mean + std) = 26
    "mfcc_1_mean", "mfcc_1_std", "mfcc_2_mean", "mfcc_2_std",
    "mfcc_3_mean", "mfcc_3_std", "mfcc_4_mean", "mfcc_4_std",
    "mfcc_5_mean", "mfcc_5_std", "mfcc_6_mean", "mfcc_6_std",
    "mfcc_7_mean", "mfcc_7_std", "mfcc_8_mean", "mfcc_8_std",
    "mfcc_9_mean", "mfcc_9_std", "mfcc_10_mean", "mfcc_10_std",
    "mfcc_11_mean", "mfcc_11_std", "mfcc_12_mean", "mfcc_12_std",
    "mfcc_13_mean", "mfcc_13_std",
    # 12 Chroma (mean + std) = 24
    "chroma_1_mean", "chroma_1_std", "chroma_2_mean", "chroma_2_std",
    "chroma_3_mean", "chroma_3_std", "chroma_4_mean", "chroma_4_std",
    "chroma_5_mean", "chroma_5_std", "chroma_6_mean", "chroma_6_std",
    "chroma_7_mean", "chroma_7_std", "chroma_8_mean", "chroma_8_std",
    "chroma_9_mean", "chroma_9_std", "chroma_10_mean", "chroma_10_std",
    "chroma_11_mean", "chroma_11_std", "chroma_12_mean", "chroma_12_std",
]


class SongAudioFeature(Base):
    """
    Extracted acoustic features for organic content model growth.
    """
    __tablename__ = "song_audio_features"

    song_id = Column(String(255), primary_key=True)  # JioSaavn externalTrackId
    title = Column(String(1024), nullable=True)
    artist_name = Column(String(1024), nullable=True)
    album = Column(String(512), nullable=True)
    language = Column(String(64), default="unknown", nullable=True)
    decade = Column(String(32), default="2020s", nullable=True)

    # ── 63 Audio Features ────────────────────────────────────────────────────
    tempo = Column(Float, nullable=False)
    rms_mean = Column(Float, nullable=False)
    rms_std = Column(Float, nullable=False)
    spectral_centroid_mean = Column(Float, nullable=False)
    spectral_centroid_std = Column(Float, nullable=False)
    spectral_rolloff_mean = Column(Float, nullable=False)
    spectral_rolloff_std = Column(Float, nullable=False)
    spectral_bandwidth_mean = Column(Float, nullable=False)
    spectral_bandwidth_std = Column(Float, nullable=False)
    spectral_flatness_mean = Column(Float, nullable=False)
    spectral_flatness_std = Column(Float, nullable=False)
    zero_crossing_rate_mean = Column(Float, nullable=False)
    zero_crossing_rate_std = Column(Float, nullable=False)

    # MFCCs (1..13)
    mfcc_1_mean = Column(Float, nullable=False)
    mfcc_1_std = Column(Float, nullable=False)
    mfcc_2_mean = Column(Float, nullable=False)
    mfcc_2_std = Column(Float, nullable=False)
    mfcc_3_mean = Column(Float, nullable=False)
    mfcc_3_std = Column(Float, nullable=False)
    mfcc_4_mean = Column(Float, nullable=False)
    mfcc_4_std = Column(Float, nullable=False)
    mfcc_5_mean = Column(Float, nullable=False)
    mfcc_5_std = Column(Float, nullable=False)
    mfcc_6_mean = Column(Float, nullable=False)
    mfcc_6_std = Column(Float, nullable=False)
    mfcc_7_mean = Column(Float, nullable=False)
    mfcc_7_std = Column(Float, nullable=False)
    mfcc_8_mean = Column(Float, nullable=False)
    mfcc_8_std = Column(Float, nullable=False)
    mfcc_9_mean = Column(Float, nullable=False)
    mfcc_9_std = Column(Float, nullable=False)
    mfcc_10_mean = Column(Float, nullable=False)
    mfcc_10_std = Column(Float, nullable=False)
    mfcc_11_mean = Column(Float, nullable=False)
    mfcc_11_std = Column(Float, nullable=False)
    mfcc_12_mean = Column(Float, nullable=False)
    mfcc_12_std = Column(Float, nullable=False)
    mfcc_13_mean = Column(Float, nullable=False)
    mfcc_13_std = Column(Float, nullable=False)

    # Chroma (1..12)
    chroma_1_mean = Column(Float, nullable=False)
    chroma_1_std = Column(Float, nullable=False)
    chroma_2_mean = Column(Float, nullable=False)
    chroma_2_std = Column(Float, nullable=False)
    chroma_3_mean = Column(Float, nullable=False)
    chroma_3_std = Column(Float, nullable=False)
    chroma_4_mean = Column(Float, nullable=False)
    chroma_4_std = Column(Float, nullable=False)
    chroma_5_mean = Column(Float, nullable=False)
    chroma_5_std = Column(Float, nullable=False)
    chroma_6_mean = Column(Float, nullable=False)
    chroma_6_std = Column(Float, nullable=False)
    chroma_7_mean = Column(Float, nullable=False)
    chroma_7_std = Column(Float, nullable=False)
    chroma_8_mean = Column(Float, nullable=False)
    chroma_8_std = Column(Float, nullable=False)
    chroma_9_mean = Column(Float, nullable=False)
    chroma_9_std = Column(Float, nullable=False)
    chroma_10_mean = Column(Float, nullable=False)
    chroma_10_std = Column(Float, nullable=False)
    chroma_11_mean = Column(Float, nullable=False)
    chroma_11_std = Column(Float, nullable=False)
    chroma_12_mean = Column(Float, nullable=False)
    chroma_12_std = Column(Float, nullable=False)

    # Retraining metadata
    extracted_at = Column(DateTime, server_default=func.now())
    incorporated_in_model = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("idx_audio_features_incorporated", "incorporated_in_model"),
        Index("idx_audio_features_extracted_at", "extracted_at"),
    )

    def __repr__(self):
        return f"<SongAudioFeature song_id={self.song_id!r} incorporated={self.incorporated_in_model}>"
