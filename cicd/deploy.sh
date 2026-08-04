#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/root/alter}"
cd "$APP_DIR"

docker compose up -d --build db redis
docker compose run --rm migrations alembic upgrade head
docker compose up -d --build bot
test "$(docker inspect -f '{{.State.Health.Status}}' alter_db_container)" = healthy
test "$(docker inspect -f '{{.State.Status}}' alter_redis_container)" = running
test "$(docker inspect -f '{{.State.Status}}' alter_bot)" = running
docker compose ps
