package com.mformusic.backend.service;

import com.mformusic.backend.dto.FastApiRecommendationDto;
import com.mformusic.backend.model.Song;
import com.mformusic.backend.repository.LikedSongRepository;
import com.mformusic.backend.repository.SongRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class RecommendationService {

    private final SongRepository songRepository;
    private final LikedSongRepository likedSongRepository;
    private final RestTemplate restTemplate;

    @Value("${mlops.fastapi.url:http://localhost:8000}")
    private String fastApiBaseUrl;

    @Value("${mlops.fastapi.enabled:false}")
    private boolean fastApiEnabled;

    /**
     * Fetches personalised recommendations for [userId] from the FastAPI MLOps
     * service and enriches each song_id with full metadata from MySQL.
     *
     * <p>Songs not found in MySQL (e.g. evicted from S3 cache) are silently
     * skipped. Returns an empty list on any error so the client degrades
     * gracefully to the Home feed.
     *
     * @param userId  Long user-id extracted from JWT
     * @param n       Number of recommendations to request from FastAPI
     */
    public List<Song> getRecommendations(Long userId, int n) {
        if (!fastApiEnabled) {
            log.info("FastAPI disabled (mlops.fastapi.enabled=false) — returning empty recommendation list.");
            return Collections.emptyList();
        }

        try {
            // ── 1. Call FastAPI ──────────────────────────────────────────────────
            String url = fastApiBaseUrl + "/api/v1/recommendations/" + userId + "?n=" + n;
            ResponseEntity<FastApiRecommendationDto> response =
                    restTemplate.getForEntity(url, FastApiRecommendationDto.class);

            if (!response.getStatusCode().is2xxSuccessful() || response.getBody() == null) {
                log.warn("FastAPI returned non-2xx for user {}: {}", userId, response.getStatusCode());
                return Collections.emptyList();
            }

            FastApiRecommendationDto body = response.getBody();
            List<FastApiRecommendationDto.FastApiSongRec> recs = body.getRecommendations();

            if (recs == null || recs.isEmpty()) {
                return Collections.emptyList();
            }

            log.info("FastAPI recommendations for user={}: {} tracks (source={}, model={})",
                    userId, recs.size(), body.getSource(), body.getModelVersion());

            // ── 2. Score map: externalTrackId → CF score (for rank preservation) ─
            Map<String, Double> scoreByTrackId = recs.stream()
                    .collect(Collectors.toMap(
                            FastApiRecommendationDto.FastApiSongRec::getSongId,
                            FastApiRecommendationDto.FastApiSongRec::getScore,
                            (a, b) -> a
                    ));

            // ── 3. Liked song IDs for this user ──────────────────────────────────
            Set<Long> likedIds = likedSongRepository
                    .findLikedSongsByUserId(userId)
                    .stream()
                    .map(Song::getId)
                    .collect(Collectors.toSet());

            // ── 4. Batch-fetch and enrich with MySQL metadata ─────────────────────
            List<Song> enriched = recs.stream()
                    .map(rec -> {
                        Optional<Song> opt = songRepository.findByExternalTrackId(rec.getSongId());
                        if (opt.isEmpty()) {
                            log.debug("Recommended song {} not in DB — skipping.", rec.getSongId());
                            return null;
                        }
                        Song song = opt.get();
                        // Mark liked flag (transient — not persisted)
                        song.setLiked(likedIds.contains(song.getId()));
                        return song;
                    })
                    .filter(Objects::nonNull)
                    // Preserve CF ranking by sorting on score descending
                    .sorted(Comparator.comparingDouble(
                            s -> -scoreByTrackId.getOrDefault(s.getExternalTrackId(), 0.0)
                    ))
                    .collect(Collectors.toList());

            log.info("Enriched {}/{} recommended tracks for user={}",
                    enriched.size(), recs.size(), userId);

            return enriched;

        } catch (Exception e) {
            log.warn("Failed to fetch recommendations from FastAPI (user={}, url={}): {}",
                    userId, fastApiBaseUrl, e.getMessage());
            return Collections.emptyList();
        }
    }
}
