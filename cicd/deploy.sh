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
sleep 5
test "$(docker inspect -f '{{.State.Status}}' alter_bot)" = running
test "$(docker inspect -f '{{.State.Health.Status}}' alter_bot)" = healthy
docker exec alter_bot python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ready', timeout=5)"
if ! curl --fail --silent --show-error --max-time 15 https://api.alterai.ru/ready >/dev/null; then
  echo "WARNING: public /ready check failed; container readiness is healthy"
fi
docker compose ps
trap - ERR
