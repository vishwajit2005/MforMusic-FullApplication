"""
Audio Feature Extraction Service

Downloads audio from Supabase/cloud storage URLs in streaming chunks and extracts
the exact 63 acoustic features (matching the offline dataset schema) using librosa.
"""

import logging
import os
import tempfile
from typing import Any

import librosa
import numpy as np
import requests

from app.models.song_audio_feature import FEATURE_COLUMNS_63

logger = logging.getLogger(__name__)


def extract_features_from_audio_array(y: np.ndarray, sr: int = 22050) -> dict[str, float]:
    """
    Computes the 63 acoustic features from a loaded mono audio array.
    """
    features: dict[str, float] = {}

    # 1. Tempo
    try:
        tempo_val = librosa.feature.tempo(y=y, sr=sr)
        features["tempo"] = float(np.atleast_1d(tempo_val)[0])
    except Exception:
        features["tempo"] = 120.0

    # 2. RMS
    rms = librosa.feature.rms(y=y)
    features["rms_mean"] = float(np.mean(rms))
    features["rms_std"] = float(np.std(rms))

    # 3. Spectral Centroid
    cent = librosa.feature.spectral_centroid(y=y, sr=sr)
    features["spectral_centroid_mean"] = float(np.mean(cent))
    features["spectral_centroid_std"] = float(np.std(cent))

    # 4. Spectral Rolloff
    roll = librosa.feature.spectral_rolloff(y=y, sr=sr)
    features["spectral_rolloff_mean"] = float(np.mean(roll))
    features["spectral_rolloff_std"] = float(np.std(roll))

    # 5. Spectral Bandwidth
    bw = librosa.feature.spectral_bandwidth(y=y, sr=sr)
    features["spectral_bandwidth_mean"] = float(np.mean(bw))
    features["spectral_bandwidth_std"] = float(np.std(bw))

    # 6. Spectral Flatness
    flat = librosa.feature.spectral_flatness(y=y)
    features["spectral_flatness_mean"] = float(np.mean(flat))
    features["spectral_flatness_std"] = float(np.std(flat))

    # 7. Zero Crossing Rate
    zcr = librosa.feature.zero_crossing_rate(y=y)
    features["zero_crossing_rate_mean"] = float(np.mean(zcr))
    features["zero_crossing_rate_std"] = float(np.std(zcr))

    # 8. 13 MFCCs (mean + std = 26 features)
    mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    for i in range(13):
        features[f"mfcc_{i+1}_mean"] = float(np.mean(mfccs[i]))
        features[f"mfcc_{i+1}_std"] = float(np.std(mfccs[i]))

    # 9. 12 Chroma (mean + std = 24 features)
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    for i in range(12):
        features[f"chroma_{i+1}_mean"] = float(np.mean(chroma[i]))
        features[f"chroma_{i+1}_std"] = float(np.std(chroma[i]))

    return features


def extract_features_from_url(audio_url: str, duration_sec: float = 45.0) -> dict[str, float] | None:
    """
    Streams audio from a URL to a temp file, loads the first `duration_sec` seconds,
    and extracts the 63 acoustic features.

    Returns:
        dict with 63 feature keys or None on error.
    """
    tmp_path = None
    try:
        # Create temp file
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
            tmp_path = tmp_file.name
            logger.info(f"Downloading audio stream from {audio_url} to temp file...")
            response = requests.get(audio_url, stream=True, timeout=30)
            response.raise_for_status()

            # Stream chunks (limit to ~10MB for 45s audio)
            bytes_written = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if chunk:
                    tmp_file.write(chunk)
                    bytes_written += len(chunk)
                    if bytes_written > 15 * 1024 * 1024:  # 15MB cap
                        break

        # Load audio with librosa (first 30-45 seconds)
        y, sr = librosa.load(tmp_path, sr=22050, duration=duration_sec, mono=True)
        if len(y) == 0:
            logger.warning(f"Audio array is empty for {audio_url}")
            return None

        features = extract_features_from_audio_array(y, sr)
        logger.info(f"Successfully extracted {len(features)} acoustic features from {audio_url}")
        return features

    except Exception as e:
        logger.error(f"Failed to extract audio features from {audio_url}: {e}", exc_info=True)
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
