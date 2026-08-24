"""
Content-Based Embedding Service — Phase 6

Generates 384-dimensional text embeddings for songs using
sentence-transformers (all-MiniLM-L6-v2 — 80 MB, fast CPU inference).

The embedding is built from the song's title and artist name:
  "{title} by {artist}"

These embeddings are stored in PostgreSQL via pgvector and used for:
  1. Content-based recommendation (cold-start users or as CF signal)
  2. Semantic natural-language search ("relaxing evening guitar music")
  3. Hybrid CF+content scoring

Thread safety: the model is loaded once at module import and shared.
"""

import logging
import threading

import numpy as np

logger = logging.getLogger(__name__)

# ── Lazy model loader ─────────────────────────────────────────────────────────
# sentence-transformers are large — load only when first needed, not at import

_model = None
_model_lock = threading.Lock()
_MODEL_NAME = "all-MiniLM-L6-v2"  # 384-dim, 80 MB, fast CPU


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                logger.info(f"Loading sentence-transformers model: {_MODEL_NAME}")
                try:
                    from sentence_transformers import SentenceTransformer
                    _model = SentenceTransformer(_MODEL_NAME)
                    logger.info("Sentence-transformers model loaded ✓")
                except Exception as e:
                    logger.error(f"Failed to load sentence-transformers: {e}")
                    _model = None
    return _model


# ── Embedding generation ──────────────────────────────────────────────────────

def song_to_text(title: str, artist: str | None) -> str:
    """Build the text passage to embed for a song."""
    artist_str = artist or "Unknown Artist"
    return f"{title} by {artist_str}"


def embed_song(title: str, artist: str | None) -> np.ndarray | None:
    """
    Generate a 384-dim embedding for a single song.
    Returns None if the model isn't available.
    """
    model = _get_model()
    if model is None:
        return None
    text = song_to_text(title, artist)
    try:
        vec = model.encode(text, normalize_embeddings=True)
        return vec.astype(np.float32)
    except Exception as e:
        logger.error(f"Embedding generation failed for '{title}': {e}")
        return None


def embed_query(query: str) -> np.ndarray | None:
    """
    Generate a 384-dim embedding for a free-text search query.
    Normalised so cosine similarity = dot product.
    """
    model = _get_model()
    if model is None:
        return None
    try:
        vec = model.encode(query, normalize_embeddings=True)
        return vec.astype(np.float32)
    except Exception as e:
        logger.error(f"Query embedding failed for '{query}': {e}")
        return None


def embed_batch(texts: list[str]) -> np.ndarray | None:
    """Batch-embed a list of text passages. Returns (N, 384) array."""
    model = _get_model()
    if model is None:
        return None
    try:
        vecs = model.encode(texts, normalize_embeddings=True, batch_size=64, show_progress_bar=False)
        return vecs.astype(np.float32)
    except Exception as e:
        logger.error(f"Batch embedding failed: {e}")
        return None
