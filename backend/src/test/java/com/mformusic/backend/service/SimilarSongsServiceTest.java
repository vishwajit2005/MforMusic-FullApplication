package com.mformusic.backend.service;

import com.mformusic.backend.controller.RecommendationController;
import com.mformusic.backend.model.Song;
import com.mformusic.backend.repository.SongRepository;
import com.mformusic.backend.security.UserPrincipal;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.server.ResponseStatusException;
import java.lang.reflect.Proxy;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class SimilarSongsServiceTest {
    RestTemplate http = new RestTemplate();
    MockRestServiceServer server = MockRestServiceServer.bindTo(http).build();
    List<String> lookedUp = new ArrayList<>();
    Song cached = song("cached");
    SongRepository repo = (SongRepository) Proxy.newProxyInstance(SongRepository.class.getClassLoader(),
        new Class<?>[]{SongRepository.class}, (p,m,a) -> {
            if (m.getName().equals("findByExternalTrackId")) return Optional.ofNullable(a[0].equals("cached") ? cached : null);
            throw new AssertionError("Unexpected DB mutation: " + m.getName());
        });
    ExternalMusicService external = new ExternalMusicService() {
        @Override public List<Map<String,Object>> getSongsByIds(List<String> ids) {
            lookedUp.addAll(ids);
            return ids.stream().map(id -> Map.<String,Object>of("id",id,"title","Resolved", "artistName","Artist",
                "thumbnailUrl","https://example.test/art", "audioUrl","https://example.test/audio", "duration",120)).toList();
        }
    };
    SimilarSongsService service() {
        var s = new SimilarSongsService(repo, external, http);
        ReflectionTestUtils.setField(s,"baseUrl","http://mlops.test");
        ReflectionTestUtils.setField(s,"enabled",true); return s;
    }
    Song song(String id) { Song s=new Song(); s.setExternalTrackId(id);s.setSaavnUrl("https://example.test/audio");return s; }
    String url="http://mlops.test/api/v1/recommendations/similar?user_id=7&current_song_id=current&n=8&context_song_ids=prior";

    @Test void forwardsContextResolvesMissingTracksAndPreservesRankWithoutSaving() {
        server.expect(requestTo(url)).andRespond(withSuccess("""
            {"recommendations":[{"song_id":"cached","rank":2,"score":0.8},
             {"song_id":"external","rank":1,"score":0.9},{"song_id":"current","rank":3,"score":0.7},
             {"song_id":"prior","rank":4,"score":0.6},{"song_id":"external","rank":5,"score":0.5}]}
            """, MediaType.APPLICATION_JSON));
        var result=service().getSimilar(7L,"current",List.of("prior"),8);
        assertEquals(List.of("external","cached"),result.stream().map(Song::getExternalTrackId).toList());
        assertEquals(List.of("external"),lookedUp); server.verify();
    }
    @Test void genuineEmptyStaysEmpty() {
        server.expect(requestTo(url)).andRespond(withSuccess("{\"recommendations\":[]}",MediaType.APPLICATION_JSON));
        assertTrue(service().getSimilar(7L,"current",List.of("prior"),8).isEmpty());
        assertTrue(lookedUp.isEmpty()); server.verify();
    }
    @Test void upstreamFailureIsRetryableAndNotAnEmptyResult() {
        server.expect(requestTo(url)).andRespond(withServerError());
        assertEquals(HttpStatus.SERVICE_UNAVAILABLE,assertThrows(ResponseStatusException.class,
            () -> service().getSimilar(7L,"current",List.of("prior"),8)).getStatusCode());
        server.verify();
    }
    @Test void disabledNeverCallsUpstream() {
        var s=service();ReflectionTestUtils.setField(s,"enabled",false);
        assertTrue(s.getSimilar(7L,"current",List.of(),8).isEmpty());server.verify();
    }
    @Test void controllerUsesAuthenticatedUserAndRejectsInvalidContext() {
        var controller=new RecommendationController(null,service());
        var auth=new UsernamePasswordAuthenticationToken(new UserPrincipal(7L,"test@example.invalid","test"),null);
        assertEquals(401,controller.getSimilarSongs("current",List.of(),8,null).getStatusCode().value());
        assertEquals(400,controller.getSimilarSongs("current",List.of("a","b","c","d","e"),8,auth).getStatusCode().value());
        server.expect(requestTo(url)).andRespond(withSuccess("{\"recommendations\":[]}",MediaType.APPLICATION_JSON));
        assertEquals(200,controller.getSimilarSongs("current",List.of("prior"),8,auth).getStatusCode().value());server.verify();
    }
}
