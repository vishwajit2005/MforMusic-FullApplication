package com.mformusic.backend.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Entity
@Table(
    name = "user_interactions",
    indexes = {
        @Index(name = "idx_user_interactions_user_id", columnList = "user_id"),
        @Index(name = "idx_user_interactions_song_id", columnList = "song_id"),
        @Index(name = "idx_user_interactions_created_at", columnList = "created_at")
    }
)
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UserInteraction {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false, length = 64)
    private String userId;

    @Column(name = "song_id", nullable = false, length = 255)
    private String songId;

    @Column(name = "interaction_type", nullable = false, length = 32)
    private String interactionType;

    @Column(name = "play_duration_sec")
    private Integer playDurationSec;

    @Column(name = "completion_rate")
    private Float completionRate;

    @Column(name = "session_id", length = 64)
    private String sessionId;

    @Column(name = "device_timestamp")
    private Long deviceTimestamp;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;
}