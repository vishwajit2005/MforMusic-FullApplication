package com.mformusic.backend.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.client.RestTemplate;

import java.util.concurrent.Executor;

@Configuration
public class AppConfig {

    @Bean
    public RestTemplate restTemplate() {
        return new RestTemplate();
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