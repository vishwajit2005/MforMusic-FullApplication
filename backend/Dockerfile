# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Build — Maven + JDK 21
# ─────────────────────────────────────────────────────────────────────────────
FROM eclipse-temurin:21-jdk-alpine AS builder

WORKDIR /build

# Cache Maven dependencies — only invalidated when pom.xml changes
COPY pom.xml .
COPY mvnw .
COPY .mvn .mvn

RUN chmod +x mvnw && \
    ./mvnw dependency:go-offline -q

# Copy source and build (skip tests — tests run in CI, not in Docker build)
COPY src src
RUN ./mvnw package -DskipTests -q

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Runtime — JRE 21 (slim)
# ─────────────────────────────────────────────────────────────────────────────
FROM eclipse-temurin:21-jre-alpine AS runtime

WORKDIR /app

# Non-root user for security
RUN addgroup -S mformusic && adduser -S mformusic -G mformusic
USER mformusic

# Copy only the built JAR
COPY --from=builder /build/target/*.jar app.jar

# Render passes PORT via environment variable; default 8080
EXPOSE 8080

# JVM tuning for containerized environments:
#   -XX:+UseContainerSupport  — respect cgroup memory limits
#   -XX:MaxRAMPercentage=75.0 — leave 25% for OS/JVM overhead
ENTRYPOINT ["java", \
  "-XX:+UseContainerSupport", \
  "-XX:MaxRAMPercentage=75.0", \
  "-Djava.security.egd=file:/dev/./urandom", \
  "-jar", "app.jar"]
