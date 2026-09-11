package com.mformusic.backend.capacity;

import com.mformusic.backend.model.Song;
import com.mformusic.backend.model.User;
import com.mformusic.backend.repository.SongRepository;
import com.mformusic.backend.repository.UserRepository;
import com.mformusic.backend.security.JwtUtil;
import com.mformusic.backend.service.CloudStorageService;
import com.zaxxer.hikari.HikariDataSource;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.core.env.Environment;
import org.springframework.http.*;
import org.springframework.http.client.*;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.client.RestTemplate;

import javax.sql.DataSource;
import java.io.*;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.LocalDateTime;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/** Only explicitly imported from src/test. Never packaged in the application jar. */
@TestConfiguration(proxyBeanMethods = false)
public class CapacityTestConfig {
    @Bean static org.springframework.beans.factory.config.BeanFactoryPostProcessor requireIsolatedDatabase(Environment env) {
        return beanFactory -> {
            String url=env.getProperty("spring.datasource.url", "");
            if (!url.startsWith("jdbc:mysql://127.0.0.1:") || !url.contains("/mformusic_capacity"))
                throw new IllegalStateException("Refusing non-local/non-disposable datasource before Hibernate starts");
        };
    }
    @Bean static BoundaryStub boundaryStub(Environment env) { return new BoundaryStub(env); }

    @Bean static BeanPostProcessor isolateRestTemplate(BoundaryStub stub) {
        return new BeanPostProcessor() {
            @Override public Object postProcessAfterInitialization(Object bean, String name) {
                if (bean instanceof RestTemplate template) template.setRequestFactory(stub);
                return bean;
            }
        };
    }

    @Bean @Primary CloudStorageService isolatedStorage(BoundaryStub stub) {
        return new CloudStorageService() {
            @Override public String uploadTrackFromUrl(String url, String id) {
                stub.uploads.incrementAndGet();
                BoundaryStub.pause(stub.uploadDelayMs);
                // No audio bytes or remote storage requests. Retains the real async service/transaction.
                return "http://capacity-audio.invalid/" + id + ".mp3";
            }
            @Override public void deleteTrackFromS3(String id) { }
        };
    }

    @Bean ApplicationRunner capacityFixtures(UserRepository users, SongRepository songs, JwtUtil jwt,
                                             Environment env, DataSource ds, BoundaryStub stub) {
        return args -> {
            // Fail closed: never seed a cloud/prod DB through this default runner.
            String url = ((HikariDataSource) ds).getJdbcUrl();
            if (!url.startsWith("jdbc:mysql://127.0.0.1:") || !url.contains("/mformusic_capacity"))
                throw new IllegalStateException("Capacity harness requires an isolated loopback mformusic_capacity schema");
            int userCount = env.getProperty("capacity.seed-users", Integer.class, 500);
            int songCount = env.getProperty("capacity.seed-songs", Integer.class, 2000);
            for (int i = 1; i <= songCount; i++) {
                String external = trackId(i);
                if (songs.findByExternalTrackId(external).isPresent()) continue;
                Song song = new Song(); song.setExternalTrackId(external); song.setTitle(title(i));
                song.setArtistName("Load Test Artist"); song.setDurationInSeconds(180);
                song.setSaavnUrl("http://capacity-audio.invalid/" + external + ".mp3");
                song.setThumbnailUrl(""); song.setStoredInS3(false); songs.save(song);
            }
            List<String> tokens = new ArrayList<>();
            for (int i = 1; i <= userCount; i++) {
                String email = "capacity-" + i + "@example.invalid";
                User user = users.findByEmail(email).orElseGet(() -> {
                    User u = new User(); u.setEmail(email); u.setUsername(email.split("@")[0]);
                    u.setPasswordHash("not-a-login-password"); u.setCreatedAt(LocalDateTime.now());
                    return users.save(u);
                });
                tokens.add("\"" + jwt.generateToken(user.getId(), email, user.getUsername()) + "\"");
            }
            String output = env.getProperty("capacity.tokens-file");
            if (output != null) Files.writeString(Path.of(output), "[" + String.join(",", tokens) + "]");
            System.out.println("CAPACITY_READY users=" + userCount + " songs=" + songCount
                    + " hikariMax=" + ((HikariDataSource) ds).getMaximumPoolSize());
        };
    }

    public static String trackId(int n) { return "load-" + String.format("%06d", n); }
    public static String title(int n) { return "Load Song " + String.format("%06d", n); }

    public static class BoundaryStub implements ClientHttpRequestFactory {
        public volatile long saavnDelayMs, fastapiDelayMs, uploadDelayMs;
        public volatile String fastapiMode = "ok";
        public volatile CountDownLatch forwardEntered, releaseForward;
        public final AtomicLong saavn = new AtomicLong(), fastapi = new AtomicLong(), blocked = new AtomicLong(), uploads = new AtomicLong();
        public final ConcurrentMap<String, AtomicLong> forwardingThreads = new ConcurrentHashMap<>();
        BoundaryStub(Environment env) {
            saavnDelayMs = env.getProperty("capacity.saavn-delay-ms", Long.class, 150L);
            fastapiDelayMs = env.getProperty("capacity.fastapi-delay-ms", Long.class, 50L);
            uploadDelayMs = env.getProperty("capacity.upload-delay-ms", Long.class, 250L);
        }
        public static void pause(long ms) {
            try { Thread.sleep(ms); } catch (InterruptedException e) { Thread.currentThread().interrupt(); throw new IllegalStateException(e); }
        }
        @Override public ClientHttpRequest createRequest(URI uri, HttpMethod method) {
            return new ClientHttpRequest() {
                private final HttpHeaders headers = new HttpHeaders();
                private final ByteArrayOutputStream body = new ByteArrayOutputStream();
                public HttpMethod getMethod() { return method; }
                public URI getURI() { return uri; }
                public Map<String,Object> getAttributes() { return new HashMap<>(); }
                public HttpHeaders getHeaders() { return headers; }
                public OutputStream getBody() { return body; }
                public ClientHttpResponse execute() throws IOException {
                    String payload; int status = 200;
                    if ("mformusic-api.onrender.com".equals(uri.getHost()) && "/api/search/songs".equals(uri.getPath())) {
                        saavn.incrementAndGet(); pause(saavnDelayMs);
                        String query = java.net.URLDecoder.decode(uri.getRawQuery(), StandardCharsets.UTF_8);
                        java.util.regex.Matcher match = java.util.regex.Pattern.compile("(\\d+)$").matcher(query);
                        int index = match.find() ? Integer.parseInt(match.group(1)) : 1;
                        List<String> results = new ArrayList<>();
                        for (int j=0; j<5; j++) {
                            int n=index+j;
                            results.add("{\"id\":\""+trackId(n)+"\",\"name\":\""+title(n)+"\",\"primaryArtists\":\"Load Test Artist\",\"duration\":180,\"image\":[],\"downloadUrl\":[{\"url\":\"http://capacity-audio.invalid/"+trackId(n)+".mp3\"}]}");
                        }
                        payload="{\"success\":true,\"data\":{\"results\":["+String.join(",",results)+"]}}";
                    } else if ("capacity-fastapi.invalid".equals(uri.getHost())) {
                        fastapi.incrementAndGet();
                        if (uri.getPath().endsWith("/interactions/ingest")) {
                            forwardingThreads.computeIfAbsent(Thread.currentThread().getName(), k -> new AtomicLong()).incrementAndGet();
                            CountDownLatch entered=forwardEntered, release=releaseForward;
                            if (entered != null && release != null) {
                                entered.countDown();
                                try { if (!release.await(5, TimeUnit.SECONDS)) throw new IOException("test gate expired"); }
                                catch (InterruptedException e) { Thread.currentThread().interrupt(); throw new IOException(e); }
                            }
                        }
                        if (fastapiMode.equals("refused")) throw new java.net.ConnectException("Controlled FastAPI connection refusal");
                        pause(fastapiDelayMs);
                        if (fastapiMode.equals("500")) { status=500; payload="{\"detail\":\"controlled fault\"}"; }
                        else if (uri.getPath().contains("/recommendations/")) {
                            int user=Integer.parseInt(uri.getPath().substring(uri.getPath().lastIndexOf('/')+1));
                            int count=Integer.parseInt(uri.getQuery().split("=")[1]);
                            List<String> recs=new ArrayList<>();
                            for(int j=0;j<count;j++) recs.add("{\"song_id\":\""+trackId(((user-1)*4+j)%2000+1)+"\",\"score\":"+(1.0-j*0.01)+",\"rank\":"+(j+1)+"}");
                            payload="{\"recommendations\":["+String.join(",",recs)+"],\"source\":\"test\",\"model_version\":\"stub\"}";
                        } else payload="{}";
                    } else {
                        blocked.incrementAndGet(); throw new IOException("External egress blocked by capacity harness: " + uri.getHost());
                    }
                    final int code=status; final byte[] bytes=payload.getBytes(StandardCharsets.UTF_8);
                    return new ClientHttpResponse() {
                        public HttpStatusCode getStatusCode() { return HttpStatusCode.valueOf(code); }
                        public String getStatusText() { return code==200 ? "OK" : "Controlled failure"; }
                        public void close() { }
                        public InputStream getBody() { return new ByteArrayInputStream(bytes); }
                        public HttpHeaders getHeaders() { HttpHeaders h=new HttpHeaders(); h.setContentType(MediaType.APPLICATION_JSON); return h; }
                    };
                }
            };
        }
    }
}
