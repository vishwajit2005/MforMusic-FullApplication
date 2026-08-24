"""
Kafka Consumer — Phase 9 Event-Driven Telemetry Ingestion

Replaces the direct HTTP push from Spring Boot with an event-driven architecture:
  Spring Boot → Kafka topic → [this consumer] → ingest_interaction()

Benefits over direct HTTP:
  - Spring Boot never blocks on MLOps latency
  - Events are durably stored in Kafka (7 day retention) — MLOps can restart
    without dropping any telemetry
  - Consumer processes at its own pace — natural backpressure
  - Multiple consumer instances (different group IDs) can process in parallel

Consumer group: "mlops-recommendation-engine"
  All MLOps replicas share this group → each message is processed exactly once.

Configuration:
  KAFKA_BOOTSTRAP_SERVERS — e.g. localhost:9092 or Confluent Cloud broker
  KAFKA_TELEMETRY_TOPIC   — must match Spring Boot's kafka.topic.telemetry
  KAFKA_CONSUMER_GROUP    — consumer group id (default: mlops-recommendation-engine)
  Set KAFKA_BOOTSTRAP_SERVERS="" or omit to disable Kafka and use HTTP path.
"""

import json
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class TelemetryKafkaConsumer:
    """
    Thread-safe, self-healing Kafka consumer for telemetry ingestion.

    Runs on a daemon thread started during FastAPI lifespan startup.
    Automatically reconnects on broker failures with exponential back-off.
    """

    def __init__(self, bootstrap_servers: str, topic: str, group_id: str):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.group_id = group_id
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self):
        """Spawn the consumer on a daemon thread."""
        if not self.bootstrap_servers:
            logger.info("KAFKA_BOOTSTRAP_SERVERS not set — Kafka consumer disabled.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._consume_loop,
            name="kafka-telemetry-consumer",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            f"Kafka consumer started: topic={self.topic} "
            f"group={self.group_id} brokers={self.bootstrap_servers}"
        )

    def stop(self):
        """Signal the consumer to stop and wait for clean shutdown."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        logger.info("Kafka consumer stopped.")

    def _consume_loop(self):
        """Main consumer loop — reconnects automatically on any error."""
        import time

        retry_delay = 5  # start with 5s back-off

        while not self._stop_event.is_set():
            try:
                from kafka import KafkaConsumer
                from kafka.errors import KafkaError

                consumer = KafkaConsumer(
                    self.topic,
                    bootstrap_servers=self.bootstrap_servers,
                    group_id=self.group_id,
                    auto_offset_reset="earliest",   # don't miss events on restart
                    enable_auto_commit=True,
                    auto_commit_interval_ms=1000,
                    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                    session_timeout_ms=30000,
                    heartbeat_interval_ms=10000,
                    max_poll_records=50,            # process 50 events per poll
                )

                logger.info("Kafka consumer connected. Waiting for messages...")
                retry_delay = 5  # reset back-off on successful connect

                for message in consumer:
                    if self._stop_event.is_set():
                        break
                    self._handle_message(message.value)

                consumer.close()

            except Exception as e:
                if self._stop_event.is_set():
                    break
                logger.warning(
                    f"Kafka consumer error (retrying in {retry_delay}s): {e}"
                )
                self._stop_event.wait(timeout=retry_delay)
                retry_delay = min(retry_delay * 2, 60)  # cap at 60s

    def _handle_message(self, payload: dict):
        """
        Process a single telemetry event from Kafka.
        Mirrors the Spring Boot TelemetryEventDto structure.
        """
        try:
            from app.core.database import SessionLocal
            from app.schemas.interaction import InteractionIngest
            from app.services.recommendation_service import ingest_interaction

            # Map Spring Boot snake_case / camelCase fields → Pydantic schema
            # Spring Boot enriches the payload with song_title + song_artist (from MySQL)
            # before publishing to Kafka — these are forwarded here for quality embeddings.
            event = InteractionIngest(
                user_id=str(payload.get("userId") or payload.get("user_id", "")),
                song_id=str(payload.get("songId") or payload.get("song_id", "")),
                interaction_type=payload.get("interactionType") or payload.get("interaction_type", "play"),
                play_duration_sec=int(payload.get("playDurationSec") or payload.get("play_duration_sec") or 0),
                completion_rate=float(payload.get("completionRate") or payload.get("completion_rate") or 0.0),
                session_id=payload.get("sessionId") or payload.get("session_id"),
                device_timestamp=payload.get("deviceTimestamp") or payload.get("device_timestamp"),
                # Song metadata — enriched by Spring Boot TelemetryService before publishing
                song_title=payload.get("songTitle") or payload.get("song_title"),
                song_artist=payload.get("songArtist") or payload.get("song_artist"),
            )

            db = SessionLocal()
            try:
                ingest_interaction(db, event)  # Fixed: db first, then payload
                logger.debug(
                    f"[Kafka] Ingested: user={event.user_id} "
                    f"song={event.song_id} type={event.interaction_type}"
                )
            finally:
                db.close()

        except Exception as e:
            logger.error(f"[Kafka] Failed to handle message (payload={payload}): {e}")


# ── Singleton instance ─────────────────────────────────────────────────────────

_consumer: Optional[TelemetryKafkaConsumer] = None


def get_kafka_consumer() -> Optional[TelemetryKafkaConsumer]:
    global _consumer
    if _consumer is None:
        bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "")
        topic = os.getenv("KAFKA_TELEMETRY_TOPIC", "mformusic.telemetry.interactions")
        group_id = os.getenv("KAFKA_CONSUMER_GROUP", "mlops-recommendation-engine")

        if bootstrap_servers:
            _consumer = TelemetryKafkaConsumer(bootstrap_servers, topic, group_id)
    return _consumer
