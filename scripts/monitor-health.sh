#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/root/alter}"
HEALTH_URL="${HEALTH_URL:-https://api.alterai.ru/ready}"
ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-${BOT_TOKEN:-}}"
TELEGRAM_ALERT_CHAT_ID="${TELEGRAM_ALERT_CHAT_ID:-}"
MAX_DISK_USED_PERCENT="${MAX_DISK_USED_PERCENT:-85}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-30}"
BACKUP_ENV_FILE="${BACKUP_ENV_FILE:-$PROJECT_DIR/.backup.env}"
if [[ -f "$BACKUP_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$BACKUP_ENV_FILE"
  set +a
fi
S3_ENDPOINT="${S3_ENDPOINT:-https://storage.yandexcloud.net}"
S3_REGION="${S3_REGION:-ru-central1}"
S3_PREFIX="${S3_PREFIX:-postgres}"
OFFSITE_BACKUP_MAX_AGE_HOURS="${OFFSITE_BACKUP_MAX_AGE_HOURS:-48}"

failures=()
alert() {
  local message="$1"
  echo "MONITOR ALERT: $message" >&2
  if [[ -n "$ALERT_WEBHOOK_URL" ]]; then
    curl --fail --silent --show-error --max-time 10 -X POST "$ALERT_WEBHOOK_URL" \
      -H 'Content-Type: application/json' \
      --data "{\"text\":\"ALTER alert: $message\"}" >/dev/null || true
  fi
  if [[ -n "$TELEGRAM_BOT_TOKEN" && -n "$TELEGRAM_ALERT_CHAT_ID" ]]; then
    curl --fail --silent --show-error --max-time 10 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${TELEGRAM_ALERT_CHAT_ID}" \
      --data-urlencode "text=ALTER alert: ${message}" >/dev/null || true
  fi
}

if ! curl --fail --silent --show-error --max-time 15 "$HEALTH_URL" >/dev/null; then
  failures+=("readiness check failed: $HEALTH_URL")
fi

if [[ -n "${S3_BUCKET:-}" ]] && command -v aws >/dev/null 2>&1; then
  offsite_key="$(aws s3api list-objects-v2 --bucket "$S3_BUCKET" --prefix "$S3_PREFIX/" --query 'Contents | sort_by(@, &LastModified)[-1].Key' --output text --endpoint-url "$S3_ENDPOINT" --region "$S3_REGION" 2>/dev/null || true)"
  if [[ -z "$offsite_key" || "$offsite_key" == "None" ]]; then
    failures+=("no off-site S3 backup found")
  elif ! aws s3api head-object --bucket "$S3_BUCKET" --key "$offsite_key" --endpoint-url "$S3_ENDPOINT" --region "$S3_REGION" >/dev/null 2>&1; then
    failures+=("off-site S3 backup cannot be verified")
  else
    offsite_date="$(aws s3api head-object --bucket "$S3_BUCKET" --key "$offsite_key" --query LastModified --output text --endpoint-url "$S3_ENDPOINT" --region "$S3_REGION" 2>/dev/null || true)"
    offsite_epoch="$(date -u -d "$offsite_date" +%s 2>/dev/null || echo 0)"
    if (( offsite_epoch == 0 || offsite_epoch < $(date -u -d "-${OFFSITE_BACKUP_MAX_AGE_HOURS} hours" +%s) )); then
      failures+=("latest off-site S3 backup is older than ${OFFSITE_BACKUP_MAX_AGE_HOURS}h")
    fi
  fi
elif [[ -n "${S3_BUCKET:-}" ]]; then
  failures+=("aws CLI is unavailable for off-site backup check")
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
