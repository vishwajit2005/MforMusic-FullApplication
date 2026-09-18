package com.mformusic.backend.service;

import com.mformusic.backend.model.Song;
import com.mformusic.backend.repository.*;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.MediaType;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;
import java.lang.reflect.Proxy;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class RecommendationMetadataTest {
    Map<String,Song> database=new HashMap<>();
    List<Song> saved=new ArrayList<>();
    List<String> fetched=new ArrayList<>();
    Set<String> unavailable=new HashSet<>();
    boolean offline, race;
    Song winner;
    RestTemplate http=new RestTemplate();
    MockRestServiceServer server=MockRestServiceServer.bindTo(http).build();
    SongRepository repo=(SongRepository) Proxy.newProxyInstance(SongRepository.class.getClassLoader(),new Class<?>[]{SongRepository.class},(p,m,a)-> {
        if(m.getName().equals("findByExternalTrackId"))return Optional.ofNullable(database.get(a[0]));
        if(m.getName().equals("saveAndFlush")) {
            Song song=(Song)a[0];
            assertEquals(0,song.getPlayCount());assertNull(song.getLastPlayedAt());assertFalse(song.getStoredInS3());assertNull(song.getS3Url());
            if(race) {winner=song("new",44L);winner.setPlayCount(12);database.put("new",winner);throw new DataIntegrityViolationException("duplicate");}
            song.setId(20L+saved.size());saved.add(song);database.put(song.getExternalTrackId(),song);return song;
        }
        throw new AssertionError("Unexpected side effect: "+m.getName());
    });
    LikedSongRepository likes=(LikedSongRepository) Proxy.newProxyInstance(LikedSongRepository.class.getClassLoader(),new Class<?>[]{LikedSongRepository.class},
        (p,m,a)->List.of(song("cached",1L)));
    ExternalMusicService external=new ExternalMusicService(){
        @Override public List<Map<String,Object>> getSongsByIds(List<String> ids) {
            fetched.addAll(ids);if(offline)throw new IllegalStateException("unavailable");
            return ids.stream().filter(id->!unavailable.contains(id)).map(id->Map.<String,Object>of("id",id,"title",id,
                "artistName","Artist","audioUrl","https://example.test/audio","thumbnailUrl","https://example.test/art","duration",120)).toList();
        }
    };
    Song song(String id,Long dbId){Song s=new Song();s.setExternalTrackId(id);s.setId(dbId);return s;}
    RecommendationService service(){var s=new RecommendationService(repo,likes,http,external);ReflectionTestUtils.setField(s,"fastApiEnabled",true);ReflectionTestUtils.setField(s,"fastApiBaseUrl","http://mlops.test");return s;}
    void expect(String recs){server.expect(requestTo("http://mlops.test/api/v1/recommendations/1?n=20")).andRespond(withSuccess("{\"recommendations\":"+recs+"}",MediaType.APPLICATION_JSON));}
    String rec(String id,double score){return "{\"song_id\":\""+id+"\",\"score\":"+score+",\"rank\":1}";}

    @Test void missingSongsAreBatchedSavedAndRankedWithoutRecordingPlays(){
        database.put("cached",song("cached",1L));expect("["+rec("cached",.2)+","+rec("new",.9)+","+rec("new",.9)+","+rec("other",.5)+"]");
        var result=service().getRecommendations(1L,20);
        assertEquals(List.of("new","other","cached"),result.stream().map(Song::getExternalTrackId).toList());
        assertEquals(Set.of("new","other"),new HashSet<>(fetched));assertEquals(2,saved.size());assertTrue(result.get(2).getLiked());server.verify();
    }
    @Test void cachedSongsNeedNoExternalFetch(){database.put("cached",song("cached",1L));expect("["+rec("cached",.8)+"]");assertEquals(1,service().getRecommendations(1L,20).size());assertTrue(fetched.isEmpty());assertTrue(saved.isEmpty());}
    @Test void partialLookupFailurePreservesOthers(){unavailable.add("missing");expect("["+rec("missing",.9)+","+rec("new",.8)+"]");assertEquals("new",service().getRecommendations(1L,20).get(0).getExternalTrackId());assertEquals(1,saved.size());}
    @Test void externalFailurePreservesCachedResults(){offline=true;database.put("cached",song("cached",1L));expect("["+rec("new",.9)+","+rec("cached",.8)+"]");assertEquals("cached",service().getRecommendations(1L,20).get(0).getExternalTrackId());}
    @Test void duplicateInsertUsesWinnerWithoutResettingItsPlayCount(){race=true;expect("["+rec("new",.8)+"]");var result=service().getRecommendations(1L,20);assertSame(winner,result.get(0));assertEquals(12,result.get(0).getPlayCount());assertTrue(saved.isEmpty());}
    @Test void totalFailureIsGracefullyEmpty(){offline=true;expect("["+rec("new",.8)+"]");assertTrue(service().getRecommendations(1L,20).isEmpty());}
}
