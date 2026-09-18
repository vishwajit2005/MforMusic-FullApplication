package com.mformusic.backend.service;

import com.mformusic.backend.dto.FastApiRecommendationDto;
import com.mformusic.backend.model.Song;
import com.mformusic.backend.repository.SongRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.UriComponentsBuilder;
import java.util.*;

@Service
@RequiredArgsConstructor
public class SimilarSongsService {
    private final SongRepository songs;
    private final ExternalMusicService externalMusic;
    private final RestTemplate restTemplate;
    @Value("${mlops.fastapi.url:}") private String baseUrl;
    @Value("${mlops.fastapi.enabled:false}") private boolean enabled;

    public List<Song> getSimilar(Long userId, String currentId, List<String> context, int n) {
        if (!enabled || baseUrl == null || baseUrl.isBlank()) return List.of();
        try {
            var uri = UriComponentsBuilder.fromUriString(baseUrl.replaceAll("/+$", ""))
                    .path("/api/v1/recommendations/similar")
                    .queryParam("user_id", userId).queryParam("current_song_id", currentId)
                    .queryParam("n", n);
            for (String id : context) uri.queryParam("context_song_ids", id);
            var body = restTemplate.getForObject(uri.build().encode().toUri(), FastApiRecommendationDto.class);
            if (body == null || body.getRecommendations() == null) return List.of();
            Set<String> excluded = new HashSet<>(context);
            excluded.add(currentId);
            var ids = body.getRecommendations().stream()
                    .sorted(Comparator.comparingInt(FastApiRecommendationDto.FastApiSongRec::getRank))
                    .map(FastApiRecommendationDto.FastApiSongRec::getSongId)
                    .filter(Objects::nonNull).filter(id -> !excluded.contains(id)).distinct().limit(n).toList();
            Map<String, Song> resolved = new HashMap<>();
            List<String> missing = new ArrayList<>();
            for (String id : ids) {
                var song = songs.findByExternalTrackId(id);
                if (song.isPresent()) resolved.put(id, song.get()); else missing.add(id);
            }
            for (var metadata : externalMusic.getSongsByIds(missing)) {
                Song song = new Song();
                song.setExternalTrackId((String) metadata.get("id"));
                song.setTitle((String) metadata.get("title"));
                song.setArtistName((String) metadata.get("artistName"));
                song.setThumbnailUrl((String) metadata.get("thumbnailUrl"));
                song.setSaavnUrl((String) metadata.get("audioUrl"));
                song.setDurationInSeconds(((Number) metadata.get("duration")).intValue());
                song.setPlayCount(0);
                resolved.put(song.getExternalTrackId(), song);
            }
            return ids.stream().map(resolved::get).filter(Objects::nonNull)
                    .filter(s -> (s.getS3Url() != null && !s.getS3Url().isBlank())
                            || (s.getSaavnUrl() != null && !s.getSaavnUrl().isBlank())).toList();
        } catch (Exception e) {
            // Distinguish a service failure from a legitimate empty catalogue result.
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "Similar songs temporarily unavailable");
        }
    }
}
