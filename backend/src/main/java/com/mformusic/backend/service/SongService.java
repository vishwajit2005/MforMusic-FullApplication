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

            // Trigger background upload (separate bean, proper @Async behavior)
            asyncUploadService.uploadToSupabaseAsync(song.getId(), saavnAudioUrl);
        }

        // Record per-user play history
        recordPlayHistory(userId, song);

        if (userId != null) {
            song.setLiked(likedSongRepository.existsByUserIdAndSongId(userId, song.getId()));
        }

        return song;
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

    /**
     * Hybrid search: local MySQL results first (instant), then JioSaavn results (up to 5),
     * de-duplicated by externalTrackId.
     */
    public List<Song> getHybridSearchResults(String query, Long userId) {
        List<Song> mergedResults = new ArrayList<>();
        Set<String> seenTrackIds = new HashSet<>();

        // Step 1: Local DB (fast, exact-match cached songs)
        log.info("Searching local DB for: {}", query);
        List<Song> localResults = songRepository.findByTitleContainingIgnoreCase(query);
        for (Song song : localResults) {
            if (userId != null) {
                song.setLiked(likedSongRepository.existsByUserIdAndSongId(userId, song.getId()));
            }
            mergedResults.add(song);
            seenTrackIds.add(song.getExternalTrackId());
        }
        log.info("Local results: {}", localResults.size());

        // Step 2: JioSaavn global results (add only if not already in local results)
        if (query.length() >= 2) {
            log.info("Fetching JioSaavn results for: {}", query);
            try {
                List<Map<String, Object>> externalResults = externalMusicService.searchMultipleSongs(query);
                for (Map<String, Object> data : externalResults) {
                    String trackId = (String) data.get("id");
                    if (seenTrackIds.contains(trackId)) continue;

                    Song externalSong = new Song();
                    externalSong.setExternalTrackId(trackId);
                    externalSong.setTitle((String) data.get("title"));
                    externalSong.setArtistName((String) data.get("artistName"));
                    externalSong.setDurationInSeconds(((Number) data.get("duration")).intValue());
                    externalSong.setThumbnailUrl((String) data.get("thumbnailUrl"));
                    externalSong.setSaavnUrl((String) data.get("audioUrl"));
                    externalSong.setPlayCount(0);
                    externalSong.setStoredInS3(Boolean.FALSE);

                    mergedResults.add(externalSong);
                    seenTrackIds.add(trackId);
                }
            } catch (Exception e) {
                log.warn("External search failed (showing local results only): {}", e.getMessage());
            }
        }

        log.info("Total merged results: {}", mergedResults.size());
        return mergedResults;
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