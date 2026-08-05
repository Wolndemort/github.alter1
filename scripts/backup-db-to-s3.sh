#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${BACKUP_ENV_FILE:-$PROJECT_DIR/.backup.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

: "${S3_BUCKET:?Set S3_BUCKET in .backup.env}"
: "${AWS_ACCESS_KEY_ID:?Set AWS_ACCESS_KEY_ID in .backup.env}"
: "${AWS_SECRET_ACCESS_KEY:?Set AWS_SECRET_ACCESS_KEY in .backup.env}"

S3_ENDPOINT="${S3_ENDPOINT:-https://storage.yandexcloud.net}"
S3_REGION="${S3_REGION:-ru-central1}"
S3_PREFIX="${S3_PREFIX:-postgres}"

cd "$PROJECT_DIR"
./scripts/backup-db.sh
LATEST="$(find "${BACKUP_DIR:-$PROJECT_DIR/backups}" -maxdepth 1 -type f -name 'alter-*.dump' -printf '%T@ %p\n' | sort -nr | head -n1 | cut -d' ' -f2-)"
if [[ -z "$LATEST" || ! -s "$LATEST" ]]; then
  echo "No verified database dump found" >&2
  exit 1
fi

KEY="$S3_PREFIX/$(basename "$LATEST")"
aws s3 cp "$LATEST" "s3://$S3_BUCKET/$KEY" \
  --endpoint-url "$S3_ENDPOINT" \
  --region "$S3_REGION" \
  --no-progress
aws s3api head-object \
  --bucket "$S3_BUCKET" \
  --key "$KEY" \
  --endpoint-url "$S3_ENDPOINT" \
  --region "$S3_REGION" >/dev/null
echo "Backup uploaded and verified: s3://$S3_BUCKET/$KEY"
