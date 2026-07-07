package com.mformusic.backend.model;

import jakarta.persistence.*;
import lombok.Data;
import java.time.LocalDateTime;

@Entity
@Table(name = "songs")
@Data
public class Song {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "external_track_id", unique = true, nullable = false)
    private String externalTrackId;

    @Column(nullable = false)
    private String title;

    // Artist name stored as a string for quick display (avoids a join)
    @Column(name = "artist_name", length = 255)
    private String artistName;

    private Integer durationInSeconds;

    // Fallback JioSaavn CDN URL (used when S3 file is evicted or not yet uploaded)
    @Column(name = "saavn_url", length = 1000)
    private String saavnUrl;

    // Primary cloud storage URL (null until background upload completes)
    @Column(name = "s3_url", length = 1000)
    private String s3Url;

    @Column(name = "is_stored_in_s3", nullable = false)
    private Boolean storedInS3 = Boolean.FALSE;

    // Play count used for LRU eviction (least played songs evicted first)
    @Column(name = "play_count")
    private long playCount = 0;

    // Last played timestamp (tiebreaker during eviction)
    @Column(name = "last_played_at")
    private LocalDateTime lastPlayedAt;

    @Column(name = "thumbnail_url", length = 1000)
    private String thumbnailUrl;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "artist_id")
    private Artist artist;

    @Transient
    private Boolean liked = false;
}