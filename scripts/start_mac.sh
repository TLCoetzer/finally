#!/usr/bin/env bash
# Build (if needed) and run the FinAlly container on macOS/Linux.
# Idempotent: re-running replaces the container but preserves the data volume.
set -euo pipefail

IMAGE="finally"
CONTAINER="finally"
VOLUME="finally-data"
PORT=8000
URL="http://localhost:${PORT}"

# Project root is the parent of this script's directory.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BUILD=false
OPEN=false
for arg in "$@"; do
  case "$arg" in
    --build) BUILD=true ;;
    --open)  OPEN=true ;;
    *) echo "Unknown option: $arg (use --build, --open)"; exit 1 ;;
  esac
done

if [ ! -f .env ]; then
  echo "No .env found. Copy .env.example to .env and add your OPENROUTER_API_KEY."
  exit 1
fi

# Build the image if it's missing or --build was requested.
if [ "$BUILD" = true ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Building image '$IMAGE'..."
  docker build -t "$IMAGE" .
fi

# Replace any existing container (data lives in the named volume, not here).
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "Removing existing container '$CONTAINER'..."
  docker rm -f "$CONTAINER" >/dev/null
fi

echo "Starting '$CONTAINER' on $URL ..."
docker run -d \
  --name "$CONTAINER" \
  -p "${PORT}:8000" \
  -v "${VOLUME}:/app/db" \
  --env-file .env \
  "$IMAGE" >/dev/null

echo "FinAlly is running at $URL"
if [ "$OPEN" = true ]; then
  open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || true
fi
