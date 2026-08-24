package com.mformusic.backend.config;

import com.mformusic.backend.dto.TelemetryEventDto;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaAdmin;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.JsonSerializer;

import java.util.HashMap;
import java.util.Map;

/**
 * KafkaConfig — Phase 9 Event Bus
 *
 * Declares the telemetry topic and provides the KafkaTemplate bean used
 * by {@link com.mformusic.backend.messaging.TelemetryEventProducer}.
 *
 * Topic settings:
 *   - 3 partitions: allows 3 concurrent consumers in the MLOps engine
 *   - 1 replica: suitable for single-broker local/Render dev setup;
 *     increase to 3 for Confluent Cloud / production
 *   - Retention 7 days: enough to replay events after MLOps restart
 */
@Configuration
public class KafkaConfig {

    @Value("${spring.kafka.bootstrap-servers:localhost:9092}")
    private String bootstrapServers;

    @Value("${kafka.topic.telemetry:mformusic.telemetry.interactions}")
    private String telemetryTopic;

    @Bean
    @ConditionalOnProperty(name = "kafka.telemetry.enabled", havingValue = "true")
    public KafkaAdmin kafkaAdmin() {
        Map<String, Object> configs = new HashMap<>();
        configs.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        KafkaAdmin admin = new KafkaAdmin(configs);
        admin.setFatalIfBrokerNotAvailable(false);
        return admin;
    }

    @Bean
    public ProducerFactory<String, TelemetryEventDto> producerFactory() {
        Map<String, Object> configProps = new HashMap<>();
        configProps.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        configProps.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        configProps.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, JsonSerializer.class);
        configProps.put(ProducerConfig.ACKS_CONFIG, "1");
        configProps.put(ProducerConfig.RETRIES_CONFIG, 3);
        return new DefaultKafkaProducerFactory<>(configProps);
    }

    @Bean
    public KafkaTemplate<String, TelemetryEventDto> kafkaTemplate() {
        return new KafkaTemplate<>(producerFactory());
    }

    /**
     * Auto-create the topic if it doesn't exist and Kafka is enabled.
     * Spring Kafka's KafkaAdmin picks this up automatically.
     */
    @Bean
    @ConditionalOnProperty(name = "kafka.telemetry.enabled", havingValue = "true")
    public NewTopic telemetryTopic() {
        return TopicBuilder.name(telemetryTopic)
                .partitions(3)
                .replicas(1)
                .build();
    }
}
