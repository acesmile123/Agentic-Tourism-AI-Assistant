#!/usr/bin/env bash
set -euo pipefail

: "${APP_IMAGE:?APP_IMAGE is required}"
: "${FRONTEND_IMAGE:?FRONTEND_IMAGE is required}"

docker compose -f compose.production.yaml pull
APP_IMAGE="$APP_IMAGE" FRONTEND_IMAGE="$FRONTEND_IMAGE" \
  docker compose -f compose.production.yaml run --rm migrate
APP_IMAGE="$APP_IMAGE" FRONTEND_IMAGE="$FRONTEND_IMAGE" \
  docker compose -f compose.production.yaml up -d --remove-orphans api mcp web nginx
docker image prune -f
