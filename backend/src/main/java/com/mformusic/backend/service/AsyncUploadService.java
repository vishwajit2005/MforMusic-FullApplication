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
