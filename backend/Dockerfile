# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — BUILD
#   Downloads dependencies, compiles source, and packages the fat jar.
#   Using the official Maven image bundled with Eclipse Temurin JDK 21.
# ─────────────────────────────────────────────────────────────────────────────
FROM maven:3.9.6-eclipse-temurin-21 AS builder

WORKDIR /build

# Copy the Maven wrapper and POM first so Docker can cache the dependency
# layer independently of source-code changes.
COPY pom.xml .
COPY .mvn/ .mvn/
COPY mvnw .

# Pre-download all dependencies (cached unless pom.xml changes)
RUN mvn dependency:go-offline -B --no-transfer-progress

# Copy the full source tree and build the executable fat jar.
# -DskipTests avoids running unit tests during image build; tests should be
# run separately in CI before building the production image.
COPY src/ src/
RUN mvn package -B -DskipTests --no-transfer-progress

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — RUNTIME
#   Lean JRE-only image — no Maven, no source, no intermediate artifacts.
#   Eclipse Temurin 21 on Ubuntu Jammy (LTS) for a stable, small footprint.
# ─────────────────────────────────────────────────────────────────────────────
FROM eclipse-temurin:21-jre-jammy AS runtime

# Create a non-root system user for security best practice
RUN groupadd --system appgroup && \
    useradd  --system --gid appgroup --no-create-home appuser

WORKDIR /app

# Copy only the fat jar produced by the build stage
COPY --from=builder /build/target/backend-0.0.1-SNAPSHOT.jar app.jar

# Give the non-root user ownership of the app directory
RUN chown -R appuser:appgroup /app

USER appuser

# Render.com routes external traffic to port 8080 by default
EXPOSE 8080

# ── JVM tuning for container environments ────────────────────────────────────
# -XX:+UseContainerSupport   → respect cgroup CPU/memory limits (default in 11+,
#                               explicit here for clarity)
# -XX:MaxRAMPercentage=75.0  → use 75 % of the container's RAM as heap, leaving
#                               headroom for non-heap / Metaspace / threads
# -Djava.security.egd=...    → faster SecureRandom seed on Linux (speeds startup)
ENTRYPOINT ["java", \
    "-XX:+UseContainerSupport", \
    "-XX:MaxRAMPercentage=75.0", \
    "-Djava.security.egd=file:/dev/./urandom", \
    "-jar", "app.jar"]
