#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_FILE="\${1:?Usage: restore-drill.sh /path/to/alter-YYYYMMDD-HHMMSS.dump}"
DRILL_DB="\${DRILL_DB:-alter_restore_drill}"

[[ -s "\$BACKUP_FILE" ]] || { echo "Backup is missing or empty" >&2; exit 1; }
cd "\$PROJECT_DIR"
docker compose exec -T db dropdb --if-exists -U "\${POSTGRES_USER:-postgres}" "\$DRILL_DB"
docker compose exec -T db createdb -U "\${POSTGRES_USER:-postgres}" "\$DRILL_DB"
docker compose exec -T db pg_restore -U "\${POSTGRES_USER:-postgres}" -d "\$DRILL_DB" --no-owner "\$BACKUP_FILE"
docker compose exec -T db psql -U "\${POSTGRES_USER:-postgres}" -d "\$DRILL_DB" -c "SELECT COUNT(*) FROM users;"
docker compose exec -T db dropdb -U "\${POSTGRES_USER:-postgres}" "\$DRILL_DB"
echo "Restore drill passed"
