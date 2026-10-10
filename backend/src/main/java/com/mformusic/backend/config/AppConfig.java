package com.mformusic.backend.config;

import org.springframework.context.annotation.Bean;
import org.springframework.beans.factory.annotation.Value;
import java.net.URI;
import java.util.Objects;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.client.RestTemplate;
import lombok.extern.slf4j.Slf4j;

import java.util.concurrent.Executor;

@Slf4j
@Configuration
public class AppConfig {

    @Bean
    public RestTemplate restTemplate(
            @Value("${mlops.fastapi.url:http://localhost:8000}") String mlopsUrl,
            @Value("${MLOPS_API_KEY:}") String mlopsApiKey) {

        // Explicit timeouts — critical for Render free-tier where MLOps can take
        // ~30s to wake from sleep. Without these, the default factory has no timeout
        // and hangs the backend thread indefinitely before failing silently.
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(10_000);  // 10s to establish TCP connection
        factory.setReadTimeout(55_000);     // 55s to receive first byte (covers cold-start)

        RestTemplate client = new RestTemplate(factory);

        if (!mlopsApiKey.isBlank()) {
            URI target = URI.create(mlopsUrl);
            String prefix = target.getPath().replaceAll("/+$", "") + "/";
            client.getInterceptors().add((request, body, execution) -> {
                URI uri = request.getURI();
                if (Objects.equals(target.getScheme(), uri.getScheme())
                        && Objects.equals(target.getHost(), uri.getHost())
                        && target.getPort() == uri.getPort()
                        && uri.getPath().startsWith(prefix)) {
                    request.getHeaders().set("X-MforMusic-Key", mlopsApiKey);
                }
                return execution.execute(request, body);
            });
            log.info("MLOps RestTemplate configured → {} (API key present)", mlopsUrl);
        } else {
            log.warn("MLOPS_API_KEY is blank — requests to {} will be rejected with 401 by ServiceAuth", mlopsUrl);
        }
        return client;
    }

    /**
     * Custom thread pool for @Async background uploads.
     * Limits concurrent uploads to prevent resource exhaustion.
     */
    @Bean(name = "taskExecutor")
    public Executor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);       // 2 uploads always available
        executor.setMaxPoolSize(4);        // Burst up to 4 concurrent uploads
        executor.setQueueCapacity(20);     // Queue up to 20 upload tasks
        executor.setThreadNamePrefix("bg-upload-");
        executor.initialize();
        return executor;
    }
}