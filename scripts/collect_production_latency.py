#!/usr/bin/env python3
"""Measure ALTER SSE first-token and completion latency without saving replies."""

import argparse
import json
import os
import time
from pathlib import Path

import httpx


DEFAULT_PROMPTS = (
    "Привет, ответь коротко",
    "Как быстро успокоиться перед важным разговором?",
    "Составь короткий план на сегодня",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--base-url", default=os.getenv("ALTER_BASE_URL", "https://api.alterai.ru"))
    parser.add_argument("--confirm-cost", action="store_true")
    args = parser.parse_args()
    token = os.getenv("AUTH_TOKEN", "").strip()
    if not token:
        raise SystemExit("AUTH_TOKEN is required")
    if not args.confirm_cost:
        raise SystemExit("refusing to spend credits; pass --confirm-cost explicitly")
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream", "Content-Type": "application/json"}
    records = []
    with httpx.Client(timeout=90.0, follow_redirects=True) as client:
        for index, prompt in enumerate(DEFAULT_PROMPTS, 1):
            started = time.perf_counter()
            first_token_ms = None
            statuses = []
            deltas = 0
            status = None
            error = None
            try:
                with client.stream("POST", f"{args.base_url.rstrip('/')}/api/v1/chat/stream", headers=headers, json={"message": prompt}) as response:
                    status = response.status_code
                    for line in response.iter_lines():
                        if not line.startswith("data: "):
                            continue
                        try:
                            payload = json.loads(line[6:])
                        except ValueError:
                            continue
                        if payload.get("type") == "status":
                            statuses.append(str(payload.get("status") or ""))
                        elif payload.get("type") == "delta":
                            deltas += 1
                            if first_token_ms is None:
                                first_token_ms = round((time.perf_counter() - started) * 1000, 1)
                        elif payload.get("type") == "error":
                            error = "stream_error"
            except httpx.HTTPError as exc:
                error = exc.__class__.__name__
            records.append({
                "case_id": f"latency_{index}",
                "status": status,
                "first_token_ms": first_token_ms,
                "total_ms": round((time.perf_counter() - started) * 1000, 1),
                "delta_count": deltas,
                "statuses": statuses,
                "error": error,
            })
    args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failed = sum(item["status"] != 200 or bool(item["error"]) for item in records)
    print(f"checked={len(records)} failed={failed} output={args.output}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
