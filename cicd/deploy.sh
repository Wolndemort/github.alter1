#!/usr/bin/env bash
set -Eeuo pipefail

diagnose() {
  status=$?
  echo "DEPLOY FAILED status=$status"
  docker compose ps || true
  echo "--- bot state ---"
  docker inspect -f 'status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} exit={{.State.ExitCode}} error={{.State.Error}}' alter_bot 2>/dev/null || true
  echo "--- bot logs ---"
  docker compose logs --tail=120 bot || true
  echo "--- nginx logs ---"
  docker compose logs --tail=40 alter-nginx || true
  exit "$status"
}
trap diagnose ERR

APP_DIR="${APP_DIR:-/root/alter}"
cd "$APP_DIR"

docker compose up -d --build db redis alter-nginx
docker compose run --rm migrations alembic upgrade head
docker compose up -d --build bot
test "$(docker inspect -f '{{.State.Health.Status}}' alter_db_container)" = healthy
test "$(docker inspect -f '{{.State.Status}}' alter_redis_container)" = running
test "$(docker inspect -f '{{.State.Status}}' alter_nginx)" = running
test "$(docker inspect -f '{{.State.Status}}' alter_bot)" = running

# The bot starts polling before its HTTP healthcheck has completed.  A fixed
# sleep caused healthy deploys to fail while the container was still
# `health: starting`.  Wait for the actual readiness state instead.
deadline=$((SECONDS + 120))
while true; do
  bot_status="$(docker inspect -f '{{.State.Status}}' alter_bot 2>/dev/null || true)"
  bot_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' alter_bot 2>/dev/null || true)"
  if [ "$bot_status" = running ] && [ "$bot_health" = healthy ]; then
    break
  fi
  if [ "$bot_status" != running ] || [ "$bot_health" = unhealthy ]; then
    echo "ALTER bot failed readiness: status=$bot_status health=$bot_health"
    exit 1
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "Timed out waiting for ALTER bot health: status=$bot_status health=$bot_health"
    exit 1
  fi
  sleep 3
done

# Docker may assign a new IP when bot is recreated. Nginx resolves the
# upstream name at startup and can otherwise keep the previous container IP,
# producing 502s through the shared Gym gateway. Recreate it after bot is
# healthy so its upstream DNS entry is always current.
docker compose up -d --force-recreate alter-nginx
test "$(docker inspect -f '{{.State.Status}}' alter_nginx)" = running
docker exec alter_bot python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ready', timeout=5)"
if ! curl --fail --silent --show-error --max-time 15 https://api.alterai.ru/ready >/dev/null; then
  echo "WARNING: public /ready check failed; container readiness is healthy"
fi

# Every rebuild leaves the previous untagged image behind.  Remove only
# dangling images and old build cache after the new containers are healthy;
# running images, named images, volumes, and the database are not touched.
docker image prune -f
docker builder prune -af --filter "until=168h" || true

docker compose ps
trap - ERR
