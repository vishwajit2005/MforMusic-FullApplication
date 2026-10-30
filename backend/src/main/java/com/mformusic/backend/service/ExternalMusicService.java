package com.mformusic.backend.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import com.mformusic.backend.model.Song;
import com.mformusic.backend.util.SongText;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Service
public class ExternalMusicService {

    private static final Logger log = LoggerFactory.getLogger(ExternalMusicService.class);

    private static final String SAAVN_SEARCH_URL = "https://mformusic-api.onrender.com/api/search/songs";

    /** Results used to pick the single best match for play-by-name. */
    private static final int BEST_MATCH_POOL = 10;
    /** Results fetched for the search screen (ranked afterwards by SearchRanker). */
    public static final int SEARCH_FETCH_LIMIT = 40;

    @Autowired
    private RestTemplate restTemplate;

    /** Resolve catalogue tracks by ID, never by ambiguous song title. */
    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> getSongsByIds(List<String> ids) {
        if (ids.isEmpty()) return List.of();
        String encodedIds = ids.stream()
                .map(id -> org.springframework.web.util.UriUtils.encodePathSegment(id, java.nio.charset.StandardCharsets.UTF_8))
                .collect(java.util.stream.Collectors.joining(","));
        Map<String, Object> response = restTemplate.getForObject(
                java.net.URI.create("https://mformusic-api.onrender.com/api/songs/" + encodedIds), Map.class);
        if (response == null || !Boolean.TRUE.equals(response.get("success"))) {
            throw new IllegalStateException("Song lookup unavailable");
        }
        List<Map<String, Object>> data = (List<Map<String, Object>>) response.get("data");
        if (data == null) return List.of();
        return data.stream().map(this::extractSongData).filter(java.util.Objects::nonNull)
                .filter(song -> ids.contains(song.get("id"))).toList();
    }

    /**
     * Search JioSaavn and return the single best match (used for play/cache flow).
     */
    public Map<String, Object> searchSongOnSaavn(String songName) {
        List<Map<String, Object>> results = searchMultipleSongs(songName, BEST_MATCH_POOL);
        if (results.isEmpty()) return null;
        // Prefer the closest title match over JioSaavn's raw first result.
        List<SearchRanker.Candidate> candidates = new ArrayList<>();
        for (int i = 0; i < results.size(); i++) {
            candidates.add(new SearchRanker.Candidate(toSong(results.get(i)), i, results.size(), false));
        }
        String bestId = SearchRanker.rank(songName, candidates, 1).stream()
                .findFirst().map(com.mformusic.backend.model.Song::getExternalTrackId).orElse(null);
        return results.stream().filter(r -> java.util.Objects.equals(r.get("id"), bestId))
                .findFirst().orElse(results.get(0));
    }

    /** Backwards-compatible: up to SEARCH_FETCH_LIMIT matches. */
    public List<Map<String, Object>> searchMultipleSongs(String query) {
        return searchMultipleSongs(query, SEARCH_FETCH_LIMIT);
    }

    /** JioSaavn returns about 10 songs per page regardless of the requested limit. */
    private static final int SAAVN_PAGE_SIZE = 10;
    private static final java.util.concurrent.ExecutorService SEARCH_POOL =
            java.util.concurrent.Executors.newFixedThreadPool(8, r -> {
                Thread t = new Thread(r, "saavn-search");
                t.setDaemon(true);
                return t;
            });

    /**
     * Search JioSaavn and return up to [limit] matches in JioSaavn's order.
     * Fetches ceil(limit / 10) pages in parallel and merges them (duplicates removed),
     * because the upstream API caps each page at ~10 results.
     */
    public List<Map<String, Object>> searchMultipleSongs(String query, int limit) {
        int pages = Math.max(1, (limit + SAAVN_PAGE_SIZE - 1) / SAAVN_PAGE_SIZE);
        List<java.util.concurrent.CompletableFuture<List<Map<String, Object>>>> futures = new ArrayList<>();
        for (int page = 0; page < pages; page++) {
            final int p = page;
            futures.add(pages == 1
                    ? java.util.concurrent.CompletableFuture.completedFuture(fetchSearchPage(query, p))
                    : java.util.concurrent.CompletableFuture.supplyAsync(() -> fetchSearchPage(query, p), SEARCH_POOL));
        }
        List<Map<String, Object>> output = new ArrayList<>();
        java.util.Set<Object> seen = new java.util.HashSet<>();
        for (var future : futures) {
            List<Map<String, Object>> pageResults;
            try {
                pageResults = future.get(20, java.util.concurrent.TimeUnit.SECONDS);
            } catch (Exception e) {
                log.warn("JioSaavn search page failed: {}", e.getMessage());
                continue;
            }
            for (Map<String, Object> song : pageResults) {
                if (output.size() >= limit) break;
                if (seen.add(song.get("id"))) output.add(song);
            }
        }
        return output;
    }

    private List<Map<String, Object>> fetchSearchPage(String query, int page) {
        List<Map<String, Object>> output = new ArrayList<>();
        java.net.URI url = org.springframework.web.util.UriComponentsBuilder.fromUriString(SAAVN_SEARCH_URL)
                .queryParam("page", page)
                .queryParam("limit", SAAVN_PAGE_SIZE)
                .queryParam("query", query)   // kept last: existing test harness parses the query tail
                .build().encode().toUri();

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

            if (results == null) return output;
            for (Map<String, Object> item : results) {
                Map<String, Object> songData = extractSongData(item);
                if (songData != null) output.add(songData);
            }
        } catch (Exception e) {
            log.error("JioSaavn API call failed (page {}): {}", page, e.getMessage());
        }
        return output;
    }

    /** Map a JioSaavn result (from extractSongData) to an unsaved Song for display/ranking. */
    public static Song toSong(Map<String, Object> data) {
        Song song = new Song();
        song.setExternalTrackId((String) data.get("id"));
        song.setTitle((String) data.get("title"));
        song.setArtistName((String) data.get("artistName"));
        Object duration = data.get("duration");
        song.setDurationInSeconds(duration instanceof Number n ? n.intValue() : 0);
        song.setThumbnailUrl((String) data.get("thumbnailUrl"));
        song.setSaavnUrl((String) data.get("audioUrl"));
        song.setPlayCount(0);
        song.setStoredInS3(Boolean.FALSE);
        return song;
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

            Object rawTitle = item.getOrDefault("name", "Unknown");
            return Map.of(
                    "id", item.get("id").toString(),
                    "title", SongText.unescape(String.valueOf(rawTitle)),
                    "artistName", SongText.unescape(artistName),
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