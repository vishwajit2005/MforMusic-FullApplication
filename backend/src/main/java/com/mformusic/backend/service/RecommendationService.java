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

import java.util.Comparator;
import java.util.List;
import java.util.HashSet;
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
    private final ExternalMusicService externalMusicService;

    @Value("${mlops.fastapi.url:http://localhost:8000}")
    private String fastApiBaseUrl;

    @Value("${mlops.fastapi.enabled:false}")
    private boolean fastApiEnabled;

    public record Result(List<Song> songs, String status) {}

    /**
     * Fetches personalised recommendations for [userId] from the FastAPI MLOps
     * service and enriches each song_id with full metadata from MySQL.
     *
     * <p>Missing metadata is batch-resolved by exact external ID and cached without
     * recording a play. Individual lookup failures preserve the remaining results.
     *
     * @param userId  Long user-id extracted from JWT
     * @param n       Number of recommendations to request from FastAPI
     */
    // Preserve the existing graceful-empty contract for internal/older callers.
    public List<Song> getRecommendations(Long userId, int n) {
        return getRecommendationResult(userId, n).songs();
    }

    public Result getRecommendationResult(Long userId, int n) {
        if (!fastApiEnabled) {
            log.info("FastAPI disabled (mlops.fastapi.enabled=false) — returning empty recommendation list.");
            return new Result(List.of(), "unavailable");
        }

        try {
            // ── 1. Call FastAPI ──────────────────────────────────────────────────
            String url = fastApiBaseUrl + "/api/v1/recommendations/" + userId + "?n=" + n;
            ResponseEntity<FastApiRecommendationDto> response =
                    restTemplate.getForEntity(url, FastApiRecommendationDto.class);

            if (!response.getStatusCode().is2xxSuccessful() || response.getBody() == null) {
                log.warn("FastAPI returned non-2xx for user {}: {}", userId, response.getStatusCode());
                return new Result(List.of(), "unavailable");
            }

            FastApiRecommendationDto body = response.getBody();
            List<FastApiRecommendationDto.FastApiSongRec> recs = body.getRecommendations();

            if (recs == null) return new Result(List.of(), "unavailable");
            if (recs.isEmpty()) return new Result(List.of(), "empty");

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

            // Resolve metadata independently of whether a recommendation was played before.
            Map<String, Song> resolved = new java.util.HashMap<>();
            List<String> missing = new java.util.ArrayList<>();
            for (String id : scoreByTrackId.keySet()) {
                Optional<Song> existing = songRepository.findByExternalTrackId(id);
                if (existing.isPresent()) resolved.put(id, existing.get()); else missing.add(id);
            }
            if (!missing.isEmpty()) {
                try {
                    // One exact-ID batch request, not one blocking request per result.
                    for (Map<String, Object> metadata : externalMusicService.getSongsByIds(missing)) {
                        String id = (String) metadata.get("id");
                        if (!missing.contains(id) || resolved.containsKey(id)) continue;
                        try {
                            Song song = new Song();
                            song.setExternalTrackId(id);
                            song.setTitle((String) metadata.get("title"));
                            song.setArtistName((String) metadata.get("artistName"));
                            song.setThumbnailUrl((String) metadata.get("thumbnailUrl"));
                            song.setDurationInSeconds(((Number) metadata.get("duration")).intValue());
                            song.setSaavnUrl((String) metadata.get("audioUrl"));
                            if (song.getTitle() == null || song.getSaavnUrl() == null || song.getSaavnUrl().isBlank()) {
                                throw new IllegalArgumentException("Missing playable song metadata");
                            }
                            // Metadata cache only: no play count, timestamp, upload or history event.
                            song.setPlayCount(0);
                            song.setStoredInS3(false);
                            song.setLastPlayedAt(null);
                            try {
                                song = songRepository.saveAndFlush(song);
                            } catch (org.springframework.dao.DataIntegrityViolationException duplicate) {
                                // Another request may have inserted the same unique external ID.
                                // Repository calls own their transactions; the failed insert is rolled back.
                                song = songRepository.findByExternalTrackId(id).orElseThrow(() -> duplicate);
                            }
                            resolved.put(id, song);
                        } catch (Exception e) {
                            log.warn("Could not cache recommendation metadata for song {}: {}", id, e.getMessage());
                        }
                    }
                } catch (Exception e) {
                    log.warn("External recommendation metadata lookup failed: {}", e.getMessage());
                }
                for (String id : missing) {
                    if (!resolved.containsKey(id)) log.warn("Recommended song {} could not be resolved — skipping.", id);
                }
            }
            Set<String> seenTrackIds = new HashSet<>();
            List<Song> enriched = recs.stream()
                    .map(rec -> resolved.get(rec.getSongId()))
                    .filter(Objects::nonNull)
                    .filter(song -> seenTrackIds.add(song.getExternalTrackId()))
                    .peek(song -> song.setLiked(likedIds.contains(song.getId())))
                    .sorted(Comparator.comparingDouble(
                            song -> -scoreByTrackId.getOrDefault(song.getExternalTrackId(), 0.0)))
                    .collect(Collectors.toList());

            log.info("Enriched {}/{} recommended tracks for user={}",
                    enriched.size(), recs.size(), userId);

            return new Result(enriched, enriched.isEmpty() ? "unavailable" : "ready");

        } catch (Exception e) {
            log.warn("Failed to fetch recommendations from FastAPI (user={}, url={}): {}",
                    userId, fastApiBaseUrl, e.getClass().getSimpleName());
            return new Result(List.of(), "unavailable");
        }
    }
}
