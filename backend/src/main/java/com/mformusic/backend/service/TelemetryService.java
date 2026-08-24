package com.mformusic.backend.service;

import com.mformusic.backend.dto.TelemetryEventDto;
import com.mformusic.backend.messaging.TelemetryEventProducer;
import com.mformusic.backend.model.Song;
import com.mformusic.backend.model.UserInteraction;
import com.mformusic.backend.repository.SongRepository;
import com.mformusic.backend.repository.UserInteractionRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.time.LocalDateTime;
import java.util.Optional;

@Slf4j
@Service
@RequiredArgsConstructor
public class TelemetryService {

    private final UserInteractionRepository interactionRepository;
    private final RestTemplate restTemplate;
    private final TelemetryEventProducer kafkaProducer;
    private final SongRepository songRepository;

    @Value("${mlops.fastapi.url:http://localhost:8000}")
    private String fastApiBaseUrl;

    @Value("${mlops.fastapi.enabled:false}")
    private boolean fastApiEnabled;

    /**
     * Phase 9: When Kafka is enabled, telemetry events are published to the
     * message broker instead of making a direct HTTP call.
     * The FastAPI MLOps consumer reads from the same topic and calls
     * ingest_interaction() internally — fully decoupled from Spring Boot.
     *
     * When Kafka is disabled ({@code kafka.telemetry.enabled=false}), the
     * original direct HTTP forwarding path is used (Phase 2 behaviour).
     */
    @Value("${kafka.telemetry.enabled:false}")
    private boolean kafkaTelemetryEnabled;

    /**
     * Ingests the telemetry event: persists to MySQL, then forwards to MLOps
     * via Kafka (Phase 9) or direct HTTP (Phase 2 fallback).
     */
    public void ingestInteraction(TelemetryEventDto dto) {
        // ── 1. Enrich DTO with song metadata (for MLOps embedding quality) ─────────────
        // Look up song by externalTrackId (= dto.songId) in MySQL and attach
        // title + artist so MLOps can build a proper semantic embedding instead
        // of using the opaque JioSaavn ID as a placeholder.
        if (dto.getSongTitle() == null && dto.getSongId() != null) {
            Optional<Song> songOpt = songRepository.findByExternalTrackId(dto.getSongId());
            songOpt.ifPresent(song -> {
                dto.setSongTitle(song.getTitle());
                dto.setSongArtist(song.getArtistName());
                log.debug("Enriched telemetry DTO with song metadata: title={}, artist={}",
                        song.getTitle(), song.getArtistName());
            });
        }

        // ── 2. Persist to MySQL ─────────────────────────────────────────────────────
        UserInteraction interaction = UserInteraction.builder()
                .userId(dto.getUserId())
                .songId(dto.getSongId())
                .interactionType(dto.getInteractionType())
                .playDurationSec(dto.getPlayDurationSec())
                .completionRate(dto.getCompletionRate())
                .sessionId(dto.getSessionId())
                .deviceTimestamp(dto.getDeviceTimestamp())
                .createdAt(LocalDateTime.now())
                .build();

        interactionRepository.save(interaction);
        log.debug("Persisted telemetry interaction: user={}, song={}, type={}",
                interaction.getUserId(), interaction.getSongId(), interaction.getInteractionType());

        // ── 3. Forward to FastAPI MLOps ───────────────────────────────────────────
        if (kafkaTelemetryEnabled) {
            // Phase 9: publish to Kafka — MLOps consumer processes at its own pace
            log.info("Publishing telemetry event to Kafka (topic: mformusic.telemetry.interactions) for user={}, song={}",
                    dto.getUserId(), dto.getSongId());
            kafkaProducer.send(dto);
        } else if (fastApiEnabled) {
            // Phase 2 fallback: direct async HTTP call
            log.info("Triggering async HTTP forwarding to FastAPI for user={}, song={}, type={}",
                    dto.getUserId(), dto.getSongId(), dto.getInteractionType());
            forwardToFastApi(dto);
        } else {
            log.warn("Telemetry forwarding skipped: both Kafka and FastAPI HTTP forwarding are disabled (kafkaTelemetryEnabled=false, fastApiEnabled=false)");
        }
    }

    /**
     * Non-blocking background worker to push events to the FastAPI ingestion
     * microservice via direct HTTP (used when Kafka is disabled).
     *
     * @deprecated Prefer Kafka (Phase 9) for production. This HTTP path is kept
     *             as a development/fallback option.
     */
    @Async("taskExecutor")
    public void forwardToFastApi(TelemetryEventDto dto) {
        String targetUrl = fastApiBaseUrl + "/api/v1/interactions/ingest";
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);

            HttpEntity<TelemetryEventDto> request = new HttpEntity<>(dto, headers);
            restTemplate.postForEntity(targetUrl, request, Void.class);
            log.info("Successfully forwarded telemetry event to FastAPI via HTTP: user={}, song={}, type={}, target={}",
                    dto.getUserId(), dto.getSongId(), dto.getInteractionType(), targetUrl);
        } catch (Exception e) {
            log.error("Failed to forward telemetry event to FastAPI via HTTP at {}: user={}, song={}, error={}",
                    targetUrl, dto.getUserId(), dto.getSongId(), e.getMessage(), e);
        }
    }
}