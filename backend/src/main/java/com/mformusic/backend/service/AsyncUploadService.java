package com.mformusic.backend.service;

import com.mformusic.backend.model.Song;
import com.mformusic.backend.repository.SongRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import org.springframework.beans.factory.annotation.Qualifier;

/**
 * Separate Spring bean for @Async + @Transactional — this is necessary because
 * calling an @Async method on the same class (SongService) bypasses the proxy
 * and the transaction/async context doesn't work correctly.
 */
@Service
public class AsyncUploadService {

    private static final Logger log = LoggerFactory.getLogger(AsyncUploadService.class);

    private static final long MAX_CLOUD_SONGS_LIMIT = 550;
    private static final int EVICTION_BATCH_SIZE = 10;

    @Autowired
    private SongRepository songRepository;

    @Autowired
    private CloudStorageService cloudStorageService;

    @Autowired
    private org.springframework.web.client.RestTemplate restTemplate;

    @Autowired
    @Qualifier("taskExecutor")
    private Executor taskExecutor;

    @org.springframework.beans.factory.annotation.Value("${mlops.fastapi.url:http://localhost:8000}")
    private String fastApiBaseUrl;

    @org.springframework.beans.factory.annotation.Value("${mlops.fastapi.enabled:false}")
    private boolean fastApiEnabled;

    @Async
    @Transactional
    public void uploadToSupabaseAsync(Long songId, String sourceUrl) {
        try {
            log.info("[BG-Upload] Starting upload for song ID: {}", songId);

            checkAndEvict();

            Optional<Song> songOpt = songRepository.findById(songId);
            if (songOpt.isEmpty()) {
                log.warn("[BG-Upload] Song ID {} not found in DB, aborting.", songId);
                return;
            }

            Song song = songOpt.get();
            log.info("[BG-Upload] Uploading: {}", song.getTitle());

            String cloudUrl = cloudStorageService.uploadTrackFromUrl(sourceUrl, song.getExternalTrackId());

            if (cloudUrl != null) {
                song.setS3Url(cloudUrl);
                song.setStoredInS3(Boolean.TRUE);
                songRepository.save(song);
                log.info("[BG-Upload] ✅ Upload complete for: {}", song.getTitle());

                // Trigger audio feature extraction in FastAPI MLOps for content model growth
                triggerFeatureExtraction(song, cloudUrl);
            } else {
                log.warn("[BG-Upload] Upload returned null URL for: {}", song.getTitle());
                song.setStoredInS3(Boolean.FALSE);
                songRepository.save(song);
            }

        } catch (Exception e) {
            log.error("[BG-Upload] Failed for song ID {}: {}", songId, e.getMessage(), e);
        }
    }

    /**
     * Dispatches a non-blocking request to FastAPI to extract 63 librosa features
     * for organic growth of the content-based recommendation model.
     */
    private void triggerFeatureExtraction(Song song, String audioUrl) {
        String songId = song.getExternalTrackId();
        if (!fastApiEnabled || fastApiBaseUrl == null || fastApiBaseUrl.isBlank()) {
            log.debug("[ContentModel] Feature extraction skipped for song={}: FastAPI disabled or URL missing",
                    songId);
            return;
        }
        if (audioUrl == null || audioUrl.isBlank()) {
            log.debug("[ContentModel] Feature extraction skipped for song={}: upload URL missing",
                    songId);
            return;
        }

        try {
            String targetUrl = fastApiBaseUrl.strip().replaceAll("/+$", "")
                    + "/api/v1/content/queue-feature-extraction";
            java.util.Map<String, Object> payload = new java.util.HashMap<>();
            payload.put("song_id", songId);
            payload.put("audio_url", audioUrl);
            payload.put("title", song.getTitle());
            payload.put("artist_name", song.getArtistName());
            payload.put("language", "unknown");
            payload.put("decade", "2020s");

            org.springframework.http.HttpHeaders headers = new org.springframework.http.HttpHeaders();
            headers.setContentType(org.springframework.http.MediaType.APPLICATION_JSON);
            org.springframework.http.HttpEntity<java.util.Map<String, Object>> request =
                    new org.springframework.http.HttpEntity<>(payload, headers);

            // Submit separately: an @Async call within this bean would bypass
            // Spring's proxy. Never wait for this future or retry the request.
            CompletableFuture.runAsync(() -> {
                try {
                    var response = restTemplate.postForEntity(targetUrl, request, Void.class);
                    if (!response.getStatusCode().is2xxSuccessful()) {
                        log.warn("[ContentModel] Feature extraction rejected for song={}: HTTP {}",
                                songId, response.getStatusCode().value());
                        return;
                    }
                    log.info("[ContentModel] Feature extraction acknowledged for song={}, target={}, status={}",
                            songId, targetUrl, response.getStatusCode().value());
                } catch (Exception e) {
                    log.warn("[ContentModel] Failed to queue feature extraction for song={}: {}",
                            songId, e.getMessage());
                }
            }, taskExecutor);
            log.info("[ContentModel] Triggering content feature extraction asynchronously for song={}, target={}",
                    songId, targetUrl);
        } catch (Exception e) {
            log.warn("[ContentModel] Failed to dispatch feature extraction for song={}: {}",
                    songId, e.getMessage());
        }
    }

    /**
     * LRU eviction: when cloud limit is hit, remove the 10 least-played songs.
     * Ties in playCount broken by oldest lastPlayedAt.
     */
    private void checkAndEvict() {
        long currentCount = songRepository.countByStoredInS3True();
        if (currentCount < MAX_CLOUD_SONGS_LIMIT) return;

        log.info("[Eviction] Cloud limit reached ({}/{}). Evicting {} songs...",
                currentCount, MAX_CLOUD_SONGS_LIMIT, EVICTION_BATCH_SIZE);

        List<Song> toEvict = songRepository
                .findTop10ByStoredInS3TrueOrderByPlayCountAscLastPlayedAtAsc();

        for (Song song : toEvict) {
            try {
                cloudStorageService.deleteTrackFromS3(song.getExternalTrackId());
                song.setStoredInS3(Boolean.FALSE);
                song.setS3Url(null);
                songRepository.save(song);
                log.info("[Eviction] Evicted: {} (playCount={})", song.getTitle(), song.getPlayCount());
            } catch (Exception e) {
                log.error("[Eviction] Failed to evict {}: {}", song.getTitle(), e.getMessage());
            }
        }
    }
}
