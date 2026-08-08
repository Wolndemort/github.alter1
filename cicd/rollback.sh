#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="\${APP_DIR:-/root/alter}"
ROLLBACK_REF="\${ROLLBACK_REF:-HEAD~1}"
cd "\$APP_DIR"

git fetch origin master
git checkout --detach "\$ROLLBACK_REF"
docker compose run --rm migrations alembic upgrade head
docker compose up -d --build bot alter-nginx
sleep 5
curl --fail --silent --show-error https://api.alterai.ru/ready >/dev/null
echo "Rollback completed at \$(git rev-parse --short HEAD)"
