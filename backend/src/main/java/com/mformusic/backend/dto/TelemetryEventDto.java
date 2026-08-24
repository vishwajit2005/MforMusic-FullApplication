package com.mformusic.backend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TelemetryEventDto {

    @JsonProperty("user_id")
    private String userId;

    @NotBlank(message = "song_id must not be blank")
    @JsonProperty("song_id")
    private String songId;

    @NotBlank(message = "interaction_type must not be blank")
    @JsonProperty("interaction_type")
    private String interactionType;

    @JsonProperty("play_duration_sec")
    @Builder.Default
    private Integer playDurationSec = 0;

    @JsonProperty("completion_rate")
    @Builder.Default
    private Float completionRate = 0.0f;

    @NotBlank(message = "session_id must not be blank")
    @JsonProperty("session_id")
    private String sessionId;

    @JsonProperty("device_timestamp")
    private Long deviceTimestamp;

    // ── Song metadata — forwarded to MLOps for quality embeddings ───────────────
    // Populated by TelemetryService via a MySQL lookup on song_id (externalTrackId).
    // Optional: MLOps falls back to using song_id as placeholder if absent.
    @JsonProperty("song_title")
    private String songTitle;

    @JsonProperty("song_artist")
    private String songArtist;
}