package com.mformusic.backend.service;

import com.mformusic.backend.model.Song;
import com.mformusic.backend.model.User;
import com.mformusic.backend.model.UserPlayHistory;
import com.mformusic.backend.model.LikedSong;
import com.mformusic.backend.repository.SongRepository;
import com.mformusic.backend.repository.UserPlayHistoryRepository;
import com.mformusic.backend.repository.UserRepository;
import com.mformusic.backend.repository.LikedSongRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.time.LocalDateTime;
import java.util.*;

@Service
public class SongService {

    private static final Logger log = LoggerFactory.getLogger(SongService.class);

    @Autowired
    private SongRepository songRepository;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private UserPlayHistoryRepository userPlayHistoryRepository;

    @Autowired
    private LikedSongRepository likedSongRepository;

    @Autowired
    private ExternalMusicService externalMusicService;

    @Autowired
    private AsyncUploadService asyncUploadService;

    @Transactional
    public Song playOrCacheSong(String songName, Long userId) {
        Map<String, Object> externalData = externalMusicService.searchSongOnSaavn(songName);
        return resolveAndPlay(externalData, songName, userId);
    }

    @Transactional
    public Song playByExternalId(String externalTrackId, Long userId) {
        Map<String, Object> data = externalMusicService.getSongsByIds(List.of(externalTrackId))
                .stream().findFirst().orElse(null);
        return resolveAndPlay(data, externalTrackId, userId);
    }

    private Song resolveAndPlay(Map<String, Object> externalData, String songName, Long userId) {
        if (externalData == null) {
            log.warn("No result found on JioSaavn for: {}", songName);
            return null;
        }

        String trackId = (String) externalData.get("id");
        String saavnAudioUrl = (String) externalData.get("audioUrl");

        log.info("Resolving track: {} (externalTrackId={})", songName, trackId);

        Optional<Song> cachedSongOpt = songRepository.findByExternalTrackId(trackId);
        Song song;

        if (cachedSongOpt.isPresent()) {
            // Cache HIT — serve from DB (Supabase URL if available, else Saavn)
            song = cachedSongOpt.get();
            log.info("Cache HIT: {} — streaming from {}", song.getTitle(),
                    Boolean.TRUE.equals(song.getStoredInS3()) ? "Supabase" : "JioSaavn");
            song.setPlayCount(song.getPlayCount() + 1);
            song.setLastPlayedAt(LocalDateTime.now());
            song = songRepository.save(song);
        } else {
            // Cache MISS — save to DB immediately, return Saavn URL, upload to Supabase async
            log.info("Cache MISS: {} — saving and triggering background upload", songName);
            Song newSong = new Song();
            newSong.setExternalTrackId(trackId);
            newSong.setTitle((String) externalData.get("title"));
            newSong.setArtistName((String) externalData.get("artistName"));
            newSong.setDurationInSeconds(((Number) externalData.get("duration")).intValue());
            newSong.setThumbnailUrl((String) externalData.get("thumbnailUrl"));
            newSong.setSaavnUrl(saavnAudioUrl);
            newSong.setPlayCount(1);
            newSong.setLastPlayedAt(LocalDateTime.now());
            newSong.setStoredInS3(Boolean.FALSE);
            song = songRepository.save(newSong);
            log.info("Saved new song to DB: id={}, externalTrackId={}", song.getId(), song.getExternalTrackId());

        }

        // A cached DB row may still need its first successful upload. Schedule only
        // after commit so the separate upload transaction can see the saved song.
        if (!Boolean.TRUE.equals(song.getStoredInS3())) {
            scheduleUploadAfterCommit(song.getId(), saavnAudioUrl);
        }

        // Record per-user play history
        recordPlayHistory(userId, song);

        if (userId != null) {
            song.setLiked(likedSongRepository.existsByUserIdAndSongId(userId, song.getId()));
        }

        return song;
    }

    private void scheduleUploadAfterCommit(Long songId, String sourceUrl) {
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                try {
                    asyncUploadService.uploadToSupabaseAsync(songId, sourceUrl);
                } catch (Exception e) {
                    // The play is already committed. A full executor must not turn
                    // successful playback into an error; a later play can try again.
                    log.warn("[BG-Upload] Could not schedule upload for song ID {}: {}",
                            songId, e.getMessage());
                }
            }
        });
    }

    private void recordPlayHistory(Long userId, Song song) {
        if (userId == null) return;
        userRepository.findById(userId).ifPresent(user -> {
            UserPlayHistory history = new UserPlayHistory();
            history.setUser(user);
            history.setSong(song);
            history.setPlayedAt(LocalDateTime.now());
            userPlayHistoryRepository.save(history);
            log.debug("Recorded play history for user {} → song {}", userId, song.getTitle());
        });
    }

    /**
     * Returns the 20 most recently played unique songs for a specific user.
     */
    public List<Song> getRecentSongsForUser(Long userId) {
        // Fetch top 50 history entries (to ensure 20 unique songs after dedup)
        List<Song> rawHistory = userPlayHistoryRepository
                .findRecentSongsByUserId(userId, PageRequest.of(0, 50));

        // Deduplicate by song ID, preserving most-recent-first order
        LinkedHashMap<Long, Song> uniqueSongs = new LinkedHashMap<>();
        for (Song song : rawHistory) {
            if (song.getId() != null) {
                if (userId != null) {
                    song.setLiked(likedSongRepository.existsByUserIdAndSongId(userId, song.getId()));
                }
                uniqueSongs.putIfAbsent(song.getId(), song);
            }
            if (uniqueSongs.size() >= 20) break;
        }
        return new ArrayList<>(uniqueSongs.values());
    }

    /** Max results returned to the search screen. */
    static final int SEARCH_RESULT_LIMIT = 30;

    /**
     * Hybrid search ranked by relevance (Spotify-style): local cached songs and up to
     * 40 JioSaavn results are merged, scored against the query (exact/prefix title
     * match, all words present, artist match, small typo tolerance) and the best
     * matches returned first — so the exact song is found even when JioSaavn's own
     * top 5 does not contain it.
     */
    public List<Song> getHybridSearchResults(String query, Long userId) {
        String trimmed = query == null ? "" : query.trim();
        if (trimmed.isEmpty()) return List.of();
        List<SearchRanker.Candidate> candidates = new ArrayList<>();

        // Step 1: Local DB (title or artist)
        List<Song> localResults = songRepository
                .findTop25ByTitleContainingIgnoreCaseOrArtistNameContainingIgnoreCase(trimmed, trimmed);
        for (int i = 0; i < localResults.size(); i++) {
            candidates.add(new SearchRanker.Candidate(localResults.get(i), i, localResults.size(), true));
        }
        log.info("Local results for '{}': {}", trimmed, localResults.size());

        // Step 2: JioSaavn global results
        if (trimmed.length() >= 2) {
            try {
                List<Map<String, Object>> externalResults = externalMusicService.searchMultipleSongs(trimmed);
                for (int i = 0; i < externalResults.size(); i++) {
                    candidates.add(new SearchRanker.Candidate(
                            ExternalMusicService.toSong(externalResults.get(i)), i, externalResults.size(), false));
                }
                log.info("JioSaavn results for '{}': {}", trimmed, externalResults.size());
            } catch (Exception e) {
                log.warn("External search failed (showing local results only): {}", e.getMessage());
            }
        }

        // Local rows come first in the candidate list, so on equal score and same
        // track ID the cached row (with its DB id / like status) is the one kept.
        List<Song> ranked = SearchRanker.rank(trimmed, candidates, SEARCH_RESULT_LIMIT);
        if (userId != null) {
            for (Song song : ranked) {
                if (song.getId() != null) {
                    song.setLiked(likedSongRepository.existsByUserIdAndSongId(userId, song.getId()));
                }
            }
        }
        log.info("Total ranked results: {}", ranked.size());
        return ranked;
    }

    @Transactional
    public Song likeSong(Long songId, Long userId) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("User not found"));
        Song song = songRepository.findById(songId)
                .orElseThrow(() -> new IllegalArgumentException("Song not found"));

        Optional<LikedSong> existing = likedSongRepository.findByUserIdAndSongId(userId, songId);
        if (existing.isEmpty()) {
            LikedSong likedSong = new LikedSong();
            likedSong.setUser(user);
            likedSong.setSong(song);
            likedSong.setLikedAt(LocalDateTime.now());
            likedSongRepository.save(likedSong);
            log.info("User {} liked song {}", userId, song.getTitle());
        }

        song.setLiked(true);
        return song;
    }

    @Transactional
    public Song unlikeSong(Long songId, Long userId) {
        Song song = songRepository.findById(songId)
                .orElseThrow(() -> new IllegalArgumentException("Song not found"));

        Optional<LikedSong> existing = likedSongRepository.findByUserIdAndSongId(userId, songId);
        existing.ifPresent(likedSong -> {
            likedSongRepository.delete(likedSong);
            log.info("User {} unliked song {}", userId, song.getTitle());
        });

        song.setLiked(false);
        return song;
    }

    public List<Song> getLikedSongsForUser(Long userId) {
        List<Song> songs = likedSongRepository.findLikedSongsByUserId(userId);
        for (Song song : songs) {
            song.setLiked(true);
        }
        return songs;
    }
}