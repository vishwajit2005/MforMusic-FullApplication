package com.mformusic.backend.messaging;

import com.mformusic.backend.dto.TelemetryEventDto;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;

import java.util.concurrent.CompletableFuture;

/**
 * TelemetryEventProducer — Phase 9 Event Bus
 *
 * Publishes {@link TelemetryEventDto} to the Kafka telemetry topic.
 * The key is "{userId}:{songId}" which routes all events for the same
 * user-song pair to the same partition, enabling ordered processing.
 *
 * Send is non-blocking — failures are logged but do NOT propagate to the
 * caller. This mirrors the existing HTTP forwarding behaviour: telemetry
 * loss on infrastructure failure is acceptable; user-facing flow must not fail.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class TelemetryEventProducer {

    private final KafkaTemplate<String, TelemetryEventDto> kafkaTemplate;

    @Value("${kafka.topic.telemetry:mformusic.telemetry.interactions}")
    private String telemetryTopic;

    /**
     * Publish a telemetry event to Kafka.
     * The partition key ensures events for the same (user, song) are ordered.
     */
    public void send(TelemetryEventDto dto) {
        String key = dto.getUserId() + ":" + dto.getSongId();

        CompletableFuture<SendResult<String, TelemetryEventDto>> future =
                kafkaTemplate.send(telemetryTopic, key, dto);

        future.whenComplete((result, ex) -> {
            if (ex != null) {
                log.warn("Failed to publish telemetry event to Kafka topic={} key={}: {}",
                        telemetryTopic, key, ex.getMessage());
            } else {
                log.debug("Telemetry event published → topic={} partition={} offset={}",
                        telemetryTopic,
                        result.getRecordMetadata().partition(),
                        result.getRecordMetadata().offset());
            }
        });
    }
}
