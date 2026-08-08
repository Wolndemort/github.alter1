#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/root/alter}"
HEALTH_URL="${HEALTH_URL:-https://api.alterai.ru/ready}"
ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-}"
MAX_DISK_USED_PERCENT="${MAX_DISK_USED_PERCENT:-85}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-30}"

failures=()
alert() {
  local message="$1"
  echo "MONITOR ALERT: $message" >&2
  if [[ -n "$ALERT_WEBHOOK_URL" ]]; then
    curl --fail --silent --show-error --max-time 10 -X POST "$ALERT_WEBHOOK_URL" \
      -H 'Content-Type: application/json' \
      --data "{\"text\":\"ALTER alert: $message\"}" >/dev/null || true
  fi
}

if ! curl --fail --silent --show-error --max-time 15 "$HEALTH_URL" >/dev/null; then
  failures+=("readiness check failed: $HEALTH_URL")
fi

if command -v docker >/dev/null 2>&1 && [[ -f "$PROJECT_DIR/docker-compose.yml" ]]; then
  if ! docker compose -f "$PROJECT_DIR/docker-compose.yml" ps --status running --services | grep -qx bot; then
    failures+=("ALTER bot is not running")
  fi
  bot_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' alter_bot 2>/dev/null || true)"
  if [[ "$bot_health" != healthy ]]; then
    failures+=("ALTER bot health is ${bot_health:-missing}")
  fi
fi

disk_used="$(df -P "$PROJECT_DIR" | awk 'NR==2 {gsub(/%/,"",$5); print $5}')"
if [[ "$disk_used" =~ ^[0-9]+$ ]] && (( disk_used >= MAX_DISK_USED_PERCENT )); then
  failures+=("disk usage is ${disk_used}%")
fi

latest_backup="$(find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'alter-*.dump' -o -name 'alter-*.sql' \) -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n1 | cut -d' ' -f2- || true)"
if [[ -z "$latest_backup" ]]; then
  failures+=("no database backup found in $BACKUP_DIR")
else
  backup_age="$(find "$latest_backup" -mmin +$((BACKUP_MAX_AGE_HOURS * 60)) -print -quit 2>/dev/null || true)"
  if [[ -n "$backup_age" ]]; then
    failures+=("latest database backup is older than ${BACKUP_MAX_AGE_HOURS}h")
  fi
fi

if (( ${#failures[@]} )); then
  for failure in "${failures[@]}"; do alert "$failure"; done
  exit 1
fi

echo "ALTER monitor OK"
