#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python -m pip install --upgrade pip
if [ "${MFORMUSIC_ROLE:-api}" = dashboard ]; then
  python -m pip install -r requirements-dashboard.txt
else
  python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.0
  python -m pip install -r requirements.txt
fi
if [ "${MFORMUSIC_ROLE:-api}" = embeddings ]; then
  export SENTENCE_TRANSFORMERS_HOME="$PWD/.model_cache"
  python -c 'from sentence_transformers import SentenceTransformer; SentenceTransformer("all-MiniLM-L6-v2")'
fi
