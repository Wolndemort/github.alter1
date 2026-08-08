#!/usr/bin/env bash
set -Eeuo pipefail

HEALTH_URL="\${HEALTH_URL:-https://api.alterai.ru/ready}"
ALERT_WEBHOOK_URL="\${ALERT_WEBHOOK_URL:-}"
if ! curl --fail --silent --show-error --max-time 15 "\$HEALTH_URL" >/dev/null; then
  message="ALTER production readiness check failed: \$HEALTH_URL"
  echo "\$message" >&2
  if [[ -n "\$ALERT_WEBHOOK_URL" ]]; then
    curl --fail --silent --show-error -X POST "\$ALERT_WEBHOOK_URL" -H 'Content-Type: application/json' --data "{\"text\":\"\$message\"}" >/dev/null
  fi
  exit 1
fi
echo "ALTER ready"
