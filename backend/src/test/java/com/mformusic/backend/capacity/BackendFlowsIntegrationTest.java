package com.mformusic.backend.capacity;

import com.mformusic.backend.BackendApplication;
import com.mformusic.backend.repository.*;
import com.mformusic.backend.security.JwtUtil;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes={BackendApplication.class,CapacityTestConfig.class},
    webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties={"capacity.seed-users=5","capacity.seed-songs=30","capacity.saavn-delay-ms=0","capacity.fastapi-delay-ms=0"})
@ActiveProfiles("capacity")
class BackendFlowsIntegrationTest {
    @LocalServerPort int port;
    @Autowired JwtUtil jwt;
    @Autowired UserRepository users;
    @Autowired SongRepository songs;
    @Autowired UserInteractionRepository interactions;
    @Autowired UserPlayHistoryRepository history;
    @Autowired CapacityTestConfig.BoundaryStub stub;
    @Autowired @org.springframework.beans.factory.annotation.Qualifier("taskExecutor")
    java.util.concurrent.Executor executor;
    final HttpClient client=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
    final tools.jackson.databind.json.JsonMapper json=tools.jackson.databind.json.JsonMapper.builder().build();
    String token;

    @BeforeEach void setup() {
        var user=users.findByEmail("capacity-1@example.invalid").orElseThrow();
        token=jwt.generateToken(user.getId(),user.getEmail(),user.getUsername());
        stub.fastapiMode="ok"; stub.fastapiDelayMs=0; stub.saavnDelayMs=0;
    }
    @AfterEach void reset() throws Exception {
        if(stub.releaseForward!=null) stub.releaseForward.countDown();
        var pool=(org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor)executor;
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(5);
        while ((pool.getActiveCount()>0 || !pool.getThreadPoolExecutor().getQueue().isEmpty())
                && System.nanoTime()<deadline) Thread.sleep(10);
        assertEquals(0,pool.getActiveCount(),"Background forwarding should finish before resetting the stub");
        stub.forwardEntered=null; stub.releaseForward=null; stub.fastapiMode="ok";
        assertEquals(0,stub.blocked.get(),"Unexpected outbound request attempted");
    }
    HttpRequest request(String method,String path,String body) {
        return HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+path))
            .timeout(Duration.ofSeconds(10)).header("Authorization","Bearer "+token)
            .header("Content-Type","application/json")
            .method(method,HttpRequest.BodyPublishers.ofString(body)).build();
    }
    HttpResponse<String> send(String method,String path,String body) throws Exception {
        return client.send(request(method,path,body),HttpResponse.BodyHandlers.ofString());
    }
    String telemetry() { return "{\"user_id\":\"spoofed\",\"song_id\":\"load-000001\",\"interaction_type\":\"play\",\"session_id\":\"integration\",\"play_duration_sec\":30,\"completion_rate\":0.5}"; }

    @Test void searchPlayLikeUnlikeAndRecentUseRealHttpSecurityAndMySql() throws Exception {
        var search=send("GET","/api/v1/songs/suggestions?query=Load%20Song%20000001","");
        assertEquals(200,search.statusCode()); assertTrue(json.readTree(search.body()).size()>0);
        long previous=history.count();
        var play=send("POST","/api/v1/songs/play?songName=Load%20Song%20000001","");
        assertEquals(200,play.statusCode());
        long id=json.readTree(play.body()).get("id").asLong();
        assertEquals(previous+1,history.count());
        assertEquals("load-000001",json.readTree(play.body()).get("externalTrackId").asText());
        var like=send("POST","/api/v1/songs/"+id+"/like","");
        assertEquals(200,like.statusCode()); assertTrue(json.readTree(like.body()).get("liked").asBoolean());
        assertTrue(send("GET","/api/v1/songs/liked","").body().contains("load-000001"));
        assertTrue(send("GET","/api/v1/songs/recent","").body().contains("load-000001"));
        var unlike=send("POST","/api/v1/songs/"+id+"/unlike","");
        assertEquals(200,unlike.statusCode()); assertFalse(json.readTree(unlike.body()).get("liked").asBoolean());
    }
    @Test void playCacheMissPersistsANewTrack() throws Exception {
        var play=send("POST","/api/v1/songs/play?songName=Load%20Song%20900001","");
        assertEquals(200,play.statusCode()); assertTrue(songs.findByExternalTrackId("load-900001").isPresent());
    }
    @Test void telemetryConnectionRefusalStillAcceptsAndPersists() throws Exception {
        stub.fastapiMode="refused"; long count=interactions.count();
        var result=send("POST","/api/v1/telemetry/interactions",telemetry());
        assertEquals(202,result.statusCode()); assertEquals(count+1,interactions.count());
        assertTrue(result.body().contains("ACCEPTED"));
        assertTrue(interactions.findAll().stream().noneMatch(i -> "spoofed".equals(i.getUserId())));
    }
    @Test void telemetryHttp500StillAcceptsAndPersists() throws Exception {
        stub.fastapiMode="500"; long count=interactions.count();
        assertEquals(202,send("POST","/api/v1/telemetry/interactions",telemetry()).statusCode());
        assertEquals(count+1,interactions.count());
    }
    @Test void invalidTelemetryIsRejectedBeforePersistence() throws Exception {
        long count=interactions.count();
        assertEquals(400,send("POST","/api/v1/telemetry/interactions","{}").statusCode());
        assertEquals(count,interactions.count());
    }
    @Test void recommendationsConnectionRefusalReturns200AndEmptyList() throws Exception {
        stub.fastapiMode="refused";
        var response=send("GET","/api/v1/recommendations?n=20","");
        assertEquals(200,response.statusCode()); assertEquals(0,json.readTree(response.body()).size());
        assertEquals("unavailable",response.headers().firstValue("X-Recommendation-Status").orElseThrow());
    }
    @Test void recommendationsHttp500Returns200AndEmptyList() throws Exception {
        stub.fastapiMode="500";
        var response=send("GET","/api/v1/recommendations?n=20","");
        assertEquals(200,response.statusCode()); assertEquals(0,json.readTree(response.body()).size());
        assertEquals("unavailable",response.headers().firstValue("X-Recommendation-Status").orElseThrow());
    }
    @Test void recommendationsEnrichRankAndClampCount() throws Exception {
        var response=send("GET","/api/v1/recommendations?n=3","");
        assertEquals(200,response.statusCode()); var rows=json.readTree(response.body());
        assertEquals("ready",response.headers().firstValue("X-Recommendation-Status").orElseThrow());
        assertEquals(3,rows.size()); assertEquals("load-000001",rows.get(0).get("externalTrackId").asText());
        assertEquals(1,json.readTree(send("GET","/api/v1/recommendations?n=0","").body()).size());
    }
    @Test @Tag("async-contract") void telemetryAcceptanceMustNotWaitForFastApiForward() throws Exception {
        stub.forwardEntered=new CountDownLatch(1); stub.releaseForward=new CountDownLatch(1);
        var future=client.sendAsync(request("POST","/api/v1/telemetry/interactions",telemetry()),HttpResponse.BodyHandlers.ofString());
        try {
            assertTrue(stub.forwardEntered.await(3,TimeUnit.SECONDS),"Forward should start");
            // The downstream is held at a latch; true fire-and-forget returns before it is released.
            var response=assertDoesNotThrow(() -> future.get(500,TimeUnit.MILLISECONDS),
                "Telemetry acceptance must not wait for downstream forwarding");
            assertEquals(202,response.statusCode());
        } finally { stub.releaseForward.countDown(); future.get(5,TimeUnit.SECONDS); }
    }
}
