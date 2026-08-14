#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_FILE="${1:?Usage: restore-drill.sh /path/to/alter-YYYYMMDD-HHMMSS.dump}"
DRILL_DB="${DRILL_DB:-alter_restore_drill}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-alter_project_db}"

[[ -s "$BACKUP_FILE" ]] || { echo "Backup is missing or empty" >&2; exit 1; }
[[ "$DRILL_DB" != "$POSTGRES_DB" && "$DRILL_DB" != "alter_project_db" ]] || {
  echo "Refusing to run restore drill against production database: $DRILL_DB" >&2
  exit 1
}
[[ "$DRILL_DB" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || {
  echo "DRILL_DB must be a simple PostgreSQL identifier" >&2
  exit 1
}
cd "$PROJECT_DIR"

cleanup() {
  docker compose exec -T db dropdb --if-exists -U "$POSTGRES_USER" "$DRILL_DB" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose exec -T db dropdb --if-exists -U "$POSTGRES_USER" "$DRILL_DB"
docker compose exec -T db createdb -U "$POSTGRES_USER" "$DRILL_DB"
docker compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$DRILL_DB" --no-owner < "$BACKUP_FILE"
docker compose exec -T db psql -U "$POSTGRES_USER" -d "$DRILL_DB" -v ON_ERROR_STOP=1 \
  -c "SELECT COUNT(*) AS users_restored FROM users;" >/dev/null
echo "Restore drill passed: $BACKUP_FILE"
