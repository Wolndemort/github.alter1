#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${SMOKE_BASE_URL:-https://api.alterai.ru}"
BASE_URL="${BASE_URL%/}"

check_status() {
  local expected="$1" url="$2"
  shift 2
  local actual=""
  for attempt in 1 2 3 4 5 6; do
    actual="$(curl --silent --show-error --max-time 15 -o /dev/null -w '%{http_code}' "$@" "$url" || true)"
    if [ "$actual" = "$expected" ]; then
      echo "SMOKE OK: $url -> $actual (attempt $attempt)"
      return 0
    fi
    sleep 5
  done
  echo "SMOKE FAILED: $url returned $actual (expected $expected)" >&2
  return 1
}

check_status 200 "$BASE_URL/health"
check_status 200 "$BASE_URL/ready"

# Public webhook must reject malformed payloads without exposing a traceback.
check_status 400 "$BASE_URL/webhooks/yookassa" \
  -H 'Content-Type: application/json' -d '{'

# Authenticated checks are opt-in so a token never needs to live in GitHub logs.
if [ -n "${SMOKE_BEARER_TOKEN:-}" ]; then
  for endpoint in account usage memory subscription; do
    check_status 200 "$BASE_URL/api/v1/$endpoint" \
      -H "Authorization: Bearer ${SMOKE_BEARER_TOKEN}"
  done
fi

echo "Production smoke passed"
