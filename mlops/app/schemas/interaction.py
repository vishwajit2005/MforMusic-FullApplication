from pydantic import BaseModel, Field
from typing import Optional


class InteractionIngest(BaseModel):
    """
    Wire contract from Spring Boot TelemetryService.forwardToFastApi().
    Field names use snake_case to match TelemetryEventDto @JsonProperty names.
    """
    user_id: str = Field(..., description="User ID (Long.toString() from JWT)")
    song_id: str = Field(..., description="JioSaavn externalTrackId — canonical song identifier")
    interaction_type: str = Field(
        ...,
        description="play | skip | like | unlike | download | playlist_add"
    )
    play_duration_sec: int = Field(default=0, ge=0)
    completion_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    session_id: Optional[str] = Field(default=None)
    device_timestamp: Optional[int] = Field(
        default=None,
        description="Epoch ms from device clock"
    )

    # ── Song metadata (optional — used for quality embeddings) ─────────────────
    # Spring Boot forwards these so MLOps can store proper title+artist in
    # song_embeddings instead of using the opaque externalTrackId as a placeholder.
    song_title: Optional[str] = Field(default=None, description="Human-readable song title")
    song_artist: Optional[str] = Field(default=None, description="Primary artist name")

    model_config = {"populate_by_name": True}


class InteractionIngestResponse(BaseModel):
    status: str
    id: int
    retrain_triggered: bool = False
