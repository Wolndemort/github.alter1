#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://api.alterai.ru}"
AUTH_TOKEN="${AUTH_TOKEN:-}"
REQUIRE_AUTH="${REQUIRE_AUTH:-false}"

status() {
  local expected="$1" url="$2"
  local actual
  actual="$(curl --silent --show-error --max-time 20 -o /dev/null -w '%{http_code}' "$url")"
  [[ "$actual" == "$expected" ]] || { echo "expected $expected from $url, got $actual" >&2; exit 1; }
}

status 200 "$BASE_URL/health"
status 200 "$BASE_URL/ready"
status 401 "$BASE_URL/api/v1/workflow"
status 401 "$BASE_URL/api/v1/action-log"
status 401 "$BASE_URL/api/v1/diagnostics/latency"
status 401 "$BASE_URL/api/v1/diagnostics/quality"

if [[ -z "$AUTH_TOKEN" ]]; then
  if [[ "$REQUIRE_AUTH" == "true" ]]; then
    echo "AUTH_TOKEN is required when REQUIRE_AUTH=true" >&2
    exit 1
  fi
  echo "public production checks passed; authenticated checks skipped"
  exit 0
fi

auth=(-H "Authorization: Bearer $AUTH_TOKEN")
curl --silent --show-error --fail --max-time 20 "${auth[@]}" "$BASE_URL/api/v1/scenarios" >/dev/null
curl --silent --show-error --fail --max-time 20 "${auth[@]}" -H 'Content-Type: application/json' \
  -d '{"workflow_id":"finish_task","goal":"Production smoke: проверить workflow"}' \
  "$BASE_URL/api/v1/workflow/start" >/dev/null
curl --silent --show-error --fail --max-time 20 "${auth[@]}" "$BASE_URL/api/v1/workflow" >/dev/null

stream_file="$(mktemp)"
trap 'rm -f "$stream_file"' EXIT
curl --silent --show-error --fail --max-time 60 "${auth[@]}" \
  -H 'Accept: text/event-stream' -H 'Content-Type: application/json' \
  -d '{"message":"Привет, ответь коротко"}' "$BASE_URL/api/v1/chat/stream" >"$stream_file"
grep -q '"type": "status"\|"type":"status"' "$stream_file"
grep -q '"type": "done"\|"type":"done"' "$stream_file"
curl --silent --show-error --fail --max-time 20 "${auth[@]}" "$BASE_URL/api/v1/action-log" >/dev/null
echo "authenticated production checks passed"
