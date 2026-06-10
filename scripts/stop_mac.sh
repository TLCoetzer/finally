#!/usr/bin/env bash
# Stop and remove the FinAlly container (macOS/Linux).
# The named volume 'finally-data' is preserved, so the database survives.
set -euo pipefail

CONTAINER="finally"

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "Stopping and removing '$CONTAINER'..."
  docker rm -f "$CONTAINER" >/dev/null
  echo "Stopped. Data volume 'finally-data' preserved."
else
  echo "Container '$CONTAINER' is not running."
fi
