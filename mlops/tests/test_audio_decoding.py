"""Decode real media bytes, including JioSaavn-style MP4 behind an .mp3 URL."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from app.models.song_audio_feature import FEATURE_COLUMNS_63
from app.services.audio_feature_extractor import extract_features_from_url


class TestAudioDecoding(unittest.TestCase):
    def test_mp3_and_mislabeled_mp4_produce_63_finite_features(self):
        # Runtime requirement: failing here prevents silently shipping an image
        # that can handle MP3 but cannot decode the actual MP4/AAC catalog audio.
        ffmpeg = shutil.which("ffmpeg")
        self.assertIsNotNone(ffmpeg, "Install FFmpeg in the MLOps runtime")
        with tempfile.TemporaryDirectory() as directory:
            for extension, codec in [("mp3", "libmp3lame"), ("m4a", "aac")]:
                with self.subTest(container=extension):
                    audio = Path(directory) / ("sample." + extension)
                    subprocess.run([
                        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                        "-c:a", codec, str(audio),
                    ], check=True, timeout=30, capture_output=True)
                    data = audio.read_bytes()
                    if extension == "m4a":
                        self.assertEqual(data[4:8], b"ftyp")
                    response = Mock()
                    response.iter_content.return_value = [data]
                    with patch("app.services.audio_feature_extractor.requests.get", return_value=response):
                        features = extract_features_from_url("https://example.invalid/track.mp3", duration_sec=2)
                    self.assertIsNotNone(features)
                    self.assertEqual(set(FEATURE_COLUMNS_63), set(features))
                    self.assertTrue(all(np.isfinite(v) for v in features.values()))

    def test_explicit_fallback_handles_native_decoder_failure(self):
        response = Mock()
        response.iter_content.return_value = [b"audio bytes"]
        samples = np.sin(np.arange(22050, dtype=np.float32) * 0.1).astype("<f4")
        result = subprocess.CompletedProcess([], 0, stdout=samples.tobytes(), stderr=b"")
        with patch("app.services.audio_feature_extractor.requests.get", return_value=response), \
             patch("app.services.audio_feature_extractor.librosa.load", side_effect=RuntimeError("unsupported format")), \
             patch("app.services.audio_feature_extractor.subprocess.run", return_value=result) as decode:
            features = extract_features_from_url("https://example.invalid/track.mp3", duration_sec=1)
        self.assertEqual(set(FEATURE_COLUMNS_63), set(features))
        args, kwargs = decode.call_args
        self.assertIn("file,pipe", args[0])
        self.assertEqual(kwargs["timeout"], 60)
        self.assertTrue(kwargs["check"])
        self.assertFalse(Path(args[0][args[0].index("-i") + 1]).exists())

    def test_decoder_failure_or_timeout_returns_none_and_cleans_temp_file(self):
        for failure in [FileNotFoundError("ffmpeg"), subprocess.TimeoutExpired("ffmpeg", 60),
                        subprocess.CalledProcessError(1, "ffmpeg")]:
            with self.subTest(error=type(failure).__name__):
                response = Mock()
                response.iter_content.return_value = [b"audio bytes"]
                with patch("app.services.audio_feature_extractor.requests.get", return_value=response), \
                     patch("app.services.audio_feature_extractor.librosa.load", side_effect=RuntimeError("format")), \
                     patch("app.services.audio_feature_extractor.subprocess.run", side_effect=failure) as decode:
                    self.assertIsNone(extract_features_from_url("https://example.invalid/track.mp3"))
                command = decode.call_args.args[0]
                self.assertFalse(Path(command[command.index("-i") + 1]).exists())

    def test_invalid_audio_fails_cleanly(self):
        response = Mock()
        response.iter_content.return_value = [b"not an audio file"]
        with patch("app.services.audio_feature_extractor.requests.get", return_value=response):
            self.assertIsNone(extract_features_from_url("https://example.invalid/invalid.mp3"))


if __name__ == "__main__":
    unittest.main()
