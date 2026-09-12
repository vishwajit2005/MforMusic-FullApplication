package com.mformusic.backend.config;

import org.springframework.context.annotation.Bean;
import org.springframework.beans.factory.annotation.Value;
import java.net.URI;
import java.util.Objects;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.client.RestTemplate;

import java.util.concurrent.Executor;

@Configuration
public class AppConfig {

    @Bean
    public RestTemplate restTemplate(
            @Value("${mlops.fastapi.url:http://localhost:8000}") String mlopsUrl,
            @Value("${MLOPS_API_KEY:}") String mlopsApiKey) {
        RestTemplate client = new RestTemplate();
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