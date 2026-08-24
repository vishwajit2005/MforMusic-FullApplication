from pydantic import BaseModel, ConfigDict
from typing import List, Literal


class SongRecommendation(BaseModel):
    song_id: str
    score: float
    rank: int


class RecommendationResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    user_id: str
    recommendations: List[SongRecommendation]
    model_version: str
    total: int
    source: Literal["collaborative_filtering", "content_based", "popular", "cold_start"]


class ModelStatusResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    trained: bool
    model_version: str
    total_interactions: int
    total_users: int
    total_songs: int
