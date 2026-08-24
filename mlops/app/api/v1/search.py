"""
Semantic Search API — Phase 6

Allows users to find music using natural language queries like:
  "relaxing evening guitar music"
  "energetic workout hip-hop"
  "sad rainy day playlist"

Strategy:
  1. Embed the user query with all-MiniLM-L6-v2 (same model used for songs)
  2. Run pgvector cosine similarity search against stored song embeddings
  3. Return ranked results by embedding similarity score

Fallback: if pgvector isn't installed or no embeddings exist yet,
return a text-based substring match from the interactions table.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.embedding_service import embed_query

logger = logging.getLogger(__name__)
router = APIRouter()


class SemanticSearchResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    song_id: str
    title: str
    artist_name: str | None
    similarity_score: float
    rank: int


class SemanticSearchResponse(BaseModel):
    query: str
    results: list[SemanticSearchResult]
    total: int
    source: str  # "semantic" | "text_fallback"


@router.post(
    "/semantic",
    response_model=SemanticSearchResponse,
    summary="Natural-language song search",
    description=(
        "Embed the query text with sentence-transformers and find songs with "
        "similar acoustic/genre profiles using pgvector cosine similarity."
    ),
)
def semantic_search(
    query: str = Query(..., min_length=2, max_length=200, description="Natural language search query"),
    n: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> SemanticSearchResponse:

    if not query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    # ── 1. Try semantic (pgvector) search ────────────────────────────────────
    query_vec = embed_query(query.strip())

    if query_vec is not None:
        try:
            results = _pgvector_search(db, query_vec, n)
            if results:
                return SemanticSearchResponse(
                    query=query,
                    results=results,
                    total=len(results),
                    source="semantic",
                )
        except Exception as e:
            logger.warning(f"pgvector search failed, falling back to text: {e}")

    # ── 2. Text-based fallback ───────────────────────────────────────────────
    logger.info(f"Semantic search fallback for query='{query}'")
    results = _text_fallback_search(db, query.strip(), n)
    return SemanticSearchResponse(
        query=query,
        results=results,
        total=len(results),
        source="text_fallback",
    )


def _pgvector_search(db: Session, query_vec, n: int) -> list[SemanticSearchResult]:
    """
    cosine_distance operator (<=>) — lower = more similar.
    Convert to similarity score: 1 - distance.
    Matches HNSW index built with vector_cosine_ops.
    """
    vec_str = "[" + ",".join(f"{v:.6f}" for v in query_vec.tolist()) + "]"

    sql = text("""
        SELECT
            song_id,
            title,
            artist_name,
            1 - (embedding <=> CAST(:vec AS vector)) AS similarity
        FROM song_embeddings
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:vec AS vector)
        LIMIT :n
    """)

    rows = db.execute(sql, {"vec": vec_str, "n": n}).fetchall()

    return [
        SemanticSearchResult(
            song_id=row.song_id,
            title=row.title,
            artist_name=row.artist_name,
            similarity_score=round(float(row.similarity), 6),
            rank=i + 1,
        )
        for i, row in enumerate(rows)
    ]


def _text_fallback_search(db: Session, query: str, n: int) -> list[SemanticSearchResult]:
    """
    Simple ILIKE text match against the song_embeddings metadata table.
    Used when pgvector isn't available or embeddings haven't been generated yet.
    """
    try:
        sql = text("""
            SELECT song_id, title, artist_name
            FROM song_embeddings
            WHERE title ILIKE :pattern OR artist_name ILIKE :pattern
            LIMIT :n
        """)
        rows = db.execute(sql, {"pattern": f"%{query}%", "n": n}).fetchall()
        return [
            SemanticSearchResult(
                song_id=row.song_id,
                title=row.title,
                artist_name=row.artist_name,
                similarity_score=0.5,
                rank=i + 1,
            )
            for i, row in enumerate(rows)
        ]
    except Exception as e:
        logger.error(f"Text fallback search also failed: {e}")
        return []
