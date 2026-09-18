# Audio decoding runtime

JioSaavn audio can contain MP4/AAC media even when its stored filename ends in
`.mp3` and the HTTP content type is `audio/mpeg`. Do not infer the codec from
those labels.

The Dockerfile installs FFmpeg. Extraction first uses the existing librosa
loader; if that fails, it explicitly invokes FFmpeg on the downloaded local
file, producing mono 22,050 Hz floating-point samples for the same 63-feature
calculation. The conversion is limited to the requested audio duration and a
60-second process timeout. Invalid audio, missing FFmpeg, and decoder timeouts
retain the existing graceful failure behavior and temporary-file cleanup.

For native Python deployments (including the current Render Python service),
FFmpeg must separately be available on PATH. The Dockerfile dependency only
applies to Docker deployments; a Python source push does not install it.
This change has not been deployed to Render.

Regression tests: `tests/test_audio_decoding.py` generates real MP3 and MP4/AAC
samples, serves both to the extractor as an `.mp3` URL, and checks all 63 finite
features. It also exercises the explicit fallback and failure/cleanup paths.

No recommendation scoring, model artifacts, feature calculations, or retraining
schedules are changed.
