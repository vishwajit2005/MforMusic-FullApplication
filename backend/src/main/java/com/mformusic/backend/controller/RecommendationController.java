package com.mformusic.backend.controller;

import com.mformusic.backend.model.Song;
import com.mformusic.backend.security.UserPrincipal;
import com.mformusic.backend.service.RecommendationService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * GET /api/v1/recommendations
 *
 * Proxies requests to the FastAPI MLOps service, enriches the
 * returned song_ids with full MySQL metadata, and returns a
 * ranked list of personalised Song objects.
 *
 * Requires a valid JWT — userId is extracted from the token,
 * not from a request parameter (prevents ID spoofing).
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/recommendations")
@RequiredArgsConstructor
public class RecommendationController {

    private final RecommendationService recommendationService;

    /**
     * GET /api/v1/recommendations?n=20
     *
     * @param n    number of tracks to return (default 20, max 50)
     * @param auth JWT authentication — userId extracted from principal
     */
    @GetMapping
    public ResponseEntity<List<Song>> getRecommendations(
            @RequestParam(defaultValue = "20") int n,
            Authentication auth
    ) {
        if (auth == null || !(auth.getPrincipal() instanceof UserPrincipal principal)) {
            return ResponseEntity.status(401).build();
        }

        // Clamp n to a safe max so clients can't request huge payloads
        int clampedN = Math.min(Math.max(n, 1), 50);
        Long userId = principal.userId();

        log.info("Recommendation request: user={}, n={}", userId, clampedN);
        List<Song> recommendations = recommendationService.getRecommendations(userId, clampedN);

        // Return 200 with [] if FastAPI is disabled or the user is in cold-start.
        // The Android client handles empty lists by showing the Home feed instead.
        return ResponseEntity.ok(recommendations);
    }
}
