package com.mformusic.backend.controller;

import com.mformusic.backend.model.Song;
import com.mformusic.backend.security.UserPrincipal;
import com.mformusic.backend.service.SongService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1/songs")
public class SongController {

    private static final Logger log = LoggerFactory.getLogger(SongController.class);

    @Autowired
    private SongService songService;

    /**
     * POST /api/v1/songs/play?songName=...
     * Plays (or caches) a song and records play in the user's history.
     */
    @PostMapping("/play")
    public ResponseEntity<Song> playOrCacheSong(@RequestParam String songName, Authentication auth) {
        Long userId = extractUserId(auth);
        log.info("Play request: '{}' by userId={}", songName, userId);
        Song song = songService.playOrCacheSong(songName, userId);
        if (song != null) {
            return ResponseEntity.ok(song);
        }
        return ResponseEntity.notFound().build();
    }

    /**
     * GET /api/v1/songs/suggestions?query=...
     * Returns hybrid (local + JioSaavn) search results.
     */
    @GetMapping("/suggestions")
    public ResponseEntity<List<Song>> getSearchSuggestions(@RequestParam String query, Authentication auth) {
        Long userId = extractUserId(auth);
        log.info("Search request: '{}' by userId={}", query, userId);
        return ResponseEntity.ok(songService.getHybridSearchResults(query, userId));
    }

    /**
     * GET /api/v1/songs/recent
     * Returns the 20 most recently played unique songs for the authenticated user.
     */
    @GetMapping("/recent")
    public ResponseEntity<List<Song>> getRecentSongs(Authentication auth) {
        Long userId = extractUserId(auth);
        if (userId == null) {
            return ResponseEntity.status(401).build();
        }
        List<Song> recent = songService.getRecentSongsForUser(userId);
        log.info("Returning {} recent songs for userId={}", recent.size(), userId);
        return ResponseEntity.ok(recent);
    }

    /**
     * POST /api/v1/songs/{songId}/like
     * Likes a song for the authenticated user.
     */
    @PostMapping("/{songId}/like")
    public ResponseEntity<Song> likeSong(@PathVariable Long songId, Authentication auth) {
        Long userId = extractUserId(auth);
        if (userId == null) {
            return ResponseEntity.status(401).build();
        }
        try {
            Song song = songService.likeSong(songId, userId);
            return ResponseEntity.ok(song);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.notFound().build();
        }
    }

    /**
     * POST /api/v1/songs/{songId}/unlike
     * Unlikes a song for the authenticated user.
     */
    @PostMapping("/{songId}/unlike")
    public ResponseEntity<Song> unlikeSong(@PathVariable Long songId, Authentication auth) {
        Long userId = extractUserId(auth);
        if (userId == null) {
            return ResponseEntity.status(401).build();
        }
        try {
            Song song = songService.unlikeSong(songId, userId);
            return ResponseEntity.ok(song);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.notFound().build();
        }
    }

    /**
     * GET /api/v1/songs/liked
     * Returns the liked songs for the authenticated user.
     */
    @GetMapping("/liked")
    public ResponseEntity<List<Song>> getLikedSongs(Authentication auth) {
        Long userId = extractUserId(auth);
        if (userId == null) {
            return ResponseEntity.status(401).build();
        }
        List<Song> likedSongs = songService.getLikedSongsForUser(userId);
        return ResponseEntity.ok(likedSongs);
    }

    private Long extractUserId(Authentication auth) {
        if (auth != null && auth.getPrincipal() instanceof UserPrincipal principal) {
            return principal.userId();
        }
        return null;
    }
}