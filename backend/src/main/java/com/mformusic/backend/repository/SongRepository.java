package com.mformusic.backend.repository;

import com.mformusic.backend.model.Song;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;
import java.util.Optional;

public interface SongRepository extends JpaRepository<Song, Long> {
    Optional<Song> findByExternalTrackId(String trackId);
    long countByStoredInS3True();
    List<Song> findByTitleContainingIgnoreCase(String title);
    List<Song> findByLastPlayedAtIsNotNullOrderByLastPlayedAtDesc(Pageable pageable);

    /**
     * LRU eviction query: returns 10 cloud-stored songs with lowest playCount,
     * with oldest lastPlayedAt as tiebreaker.
     */
    List<Song> findTop10ByStoredInS3TrueOrderByPlayCountAscLastPlayedAtAsc();
}