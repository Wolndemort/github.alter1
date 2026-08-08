#!/usr/bin/env bash
set -Eeuo pipefail

# Read-only production disk report.  It intentionally does not prune, delete,
# vacuum, or restart anything.
PROJECT_DIR="${PROJECT_DIR:-/root/alter}"

echo "== filesystem =="
df -h "$PROJECT_DIR" /

echo "== project directories =="
du -xhd1 "$PROJECT_DIR" 2>/dev/null | sort -h | tail -n 20 || true

echo "== large project files (top 30) =="
find "$PROJECT_DIR" -xdev -type f -printf '%s %p\n' 2>/dev/null \
  | sort -nr | head -n 30 \
  | awk '{printf "%.1f MiB %s\n", $1/1024/1024, substr($0, index($0,$2))}' || true

if command -v docker >/dev/null 2>&1; then
  echo "== docker system =="
  docker system df -v || true

  echo "== container log files =="
  for container in alter_bot alter_db_container alter_redis_container alter_nginx; do
    log_path="$(docker inspect -f '{{.LogPath}}' "$container" 2>/dev/null || true)"
    if [[ -n "$log_path" && -f "$log_path" ]]; then
      du -h "$log_path"
    else
      echo "$container: no json-file log path"
    fi
  done

  echo "== compose volumes =="
  docker volume ls --filter label=com.docker.compose.project=alter || true
fi

echo "== journal =="
journalctl --disk-usage 2>/dev/null || true

echo "== postgres data mounts =="
du -xhd1 /var/lib/docker/volumes 2>/dev/null | sort -h | tail -n 20 || true
