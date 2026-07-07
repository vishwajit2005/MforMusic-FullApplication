package com.mformusic.backend.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Service
public class ExternalMusicService {

    private static final Logger log = LoggerFactory.getLogger(ExternalMusicService.class);

    private static final String SAAVN_API_URL =
            "https://mformusic-api.onrender.com/api/search/songs?query=";

    private static final int MAX_EXTERNAL_RESULTS = 5;

    @Autowired
    private RestTemplate restTemplate;

    /**
     * Search JioSaavn and return the single best match (used for play/cache flow).
     */
    public Map<String, Object> searchSongOnSaavn(String songName) {
        List<Map<String, Object>> results = searchMultipleSongs(songName);
        return results.isEmpty() ? null : results.get(0);
    }

    /**
     * Search JioSaavn and return up to MAX_EXTERNAL_RESULTS matches (used for search suggestions).
     */
    public List<Map<String, Object>> searchMultipleSongs(String query) {
        List<Map<String, Object>> output = new ArrayList<>();
        String url = SAAVN_API_URL + query;

        try {
            log.info("Fetching from JioSaavn API: {}", url);
            @SuppressWarnings("unchecked")
            Map<String, Object> response = restTemplate.getForObject(url, Map.class);

            if (response == null || !Boolean.TRUE.equals(response.get("success"))) {
                log.warn("JioSaavn API returned unsuccessful response");
                return output;
            }

            @SuppressWarnings("unchecked")
            Map<String, Object> data = (Map<String, Object>) response.get("data");
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> results = (List<Map<String, Object>>) data.get("results");

            if (results == null || results.isEmpty()) return output;

            int limit = Math.min(results.size(), MAX_EXTERNAL_RESULTS);
            for (int i = 0; i < limit; i++) {
                Map<String, Object> songData = extractSongData(results.get(i));
                if (songData != null) output.add(songData);
            }

        } catch (Exception e) {
            log.error("JioSaavn API call failed: {}", e.getMessage());
        }

        return output;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> extractSongData(Map<String, Object> item) {
        try {
            // Thumbnail — last element (highest quality)
            List<Map<String, Object>> images = (List<Map<String, Object>>) item.get("image");
            String thumbnailUrl = (images != null && !images.isEmpty())
                    ? (String) images.get(images.size() - 1).get("url") : "";

            // Audio URL — last element (320kbps)
            List<Map<String, Object>> downloadUrls = (List<Map<String, Object>>) item.get("downloadUrl");
            String audioUrl = (downloadUrls != null && !downloadUrls.isEmpty())
                    ? (String) downloadUrls.get(downloadUrls.size() - 1).get("url") : "";

            // Artist name — try primaryArtists string first, then artists.primary array
            String artistName = extractArtistName(item);

            Object durationRaw = item.get("duration");
            int duration = durationRaw instanceof Number ? ((Number) durationRaw).intValue() : 0;

            return Map.of(
                    "id", item.get("id").toString(),
                    "title", item.getOrDefault("name", "Unknown"),
                    "artistName", artistName,
                    "duration", duration,
                    "audioUrl", audioUrl,
                    "thumbnailUrl", thumbnailUrl
            );
        } catch (Exception e) {
            log.warn("Failed to parse song data from JioSaavn: {}", e.getMessage());
            return null;
        }
    }

    @SuppressWarnings("unchecked")
    private String extractArtistName(Map<String, Object> item) {
        try {
            // Format 1: primaryArtists is a plain string
            Object pa = item.get("primaryArtists");
            if (pa instanceof String s && !s.isBlank()) return s;

            // Format 2: artists.primary is a list of {name, ...}
            Object artistsObj = item.get("artists");
            if (artistsObj instanceof Map<?, ?> artistsMap) {
                Object primaryObj = ((Map<String, Object>) artistsMap).get("primary");
                if (primaryObj instanceof List<?> primaryList && !primaryList.isEmpty()) {
                    Map<String, Object> first = (Map<String, Object>) primaryList.get(0);
                    return (String) first.getOrDefault("name", "");
                }
            }
        } catch (Exception ignored) {}
        return "Unknown Artist";
    }
}