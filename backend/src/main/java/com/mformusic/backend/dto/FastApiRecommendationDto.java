package com.mformusic.backend.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import java.util.List;

/**
 * Maps the JSON response from FastAPI's
 * GET /api/v1/recommendations/{userId}
 */
@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class FastApiRecommendationDto {

    @JsonProperty("user_id")
    private String userId;

    @JsonProperty("recommendations")
    private List<FastApiSongRec> recommendations;

    @JsonProperty("model_version")
    private String modelVersion;

    @JsonProperty("total")
    private int total;

    /** "collaborative_filtering" | "popular" | "cold_start" */
    @JsonProperty("source")
    private String source;

    @Data
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class FastApiSongRec {
        /** JioSaavn externalTrackId */
        @JsonProperty("song_id")
        private String songId;

        @JsonProperty("score")
        private double score;

        @JsonProperty("rank")
        private int rank;
    }
}
