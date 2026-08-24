#!/bin/bash
set -e

# Load environment variables from .env
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

echo "Starting MforMusic Backend on port ${PORT:-8080}..."
./mvnw spring-boot:run
