#!/usr/bin/env python3
"""Read-only production capability smoke; never starts paid media jobs."""

import argparse
import json
import os
import time
from pathlib import Path

import httpx


READ_ONLY_CHECKS = (
    ("account", "/api/v1/account", (200,)),
    ("memory", "/api/v1/memory", (200,)),
    ("settings", "/api/v1/settings", (200,)),
    ("action_log", "/api/v1/action-log", (200,)),
    ("workflow", "/api/v1/workflow", (200,)),
    ("reminders", "/api/v1/reminders", (200,)),
    ("calendar_status", "/api/v1/calendar/status", (200, 503)),
    ("media_capabilities", "/api/v1/media/capabilities", (200,)),
    ("audio_voices", "/api/v1/audio/voices", (200, 502, 503)),
    ("audio_models", "/api/v1/audio/models", (200, 502, 503)),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--base-url", default=os.getenv("ALTER_BASE_URL", "https://api.alterai.ru"))
    args = parser.parse_args()
    token = os.getenv("AUTH_TOKEN", "").strip()
    if not token:
        raise SystemExit("AUTH_TOKEN is required")
    headers = {"Authorization": f"Bearer {token}"}
    records = []
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for name, path, expected in READ_ONLY_CHECKS:
            started = time.perf_counter()
            try:
                response = client.get(f"{args.base_url.rstrip('/')}{path}", headers=headers)
                status = response.status_code
                ok = status in expected
                error = None if ok else f"unexpected_http_{status}"
            except httpx.HTTPError as exc:
                status, ok, error = None, False, exc.__class__.__name__
            records.append({
                "case_id": name,
                "path": path,
                "status": status,
                "ok": ok,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": error,
            })
    args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failed = sum(not item["ok"] for item in records)
    print(f"checked={len(records)} failed={failed} output={args.output}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
