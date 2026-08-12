#!/usr/bin/env python3
"""Measure production search scenarios without storing user-facing replies."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

import httpx


CASES = (
    ("local", "Где в Майкопе купить спортивные товары?"),
    ("open_now", "Какие магазины спорттоваров сейчас открыты в Майкопе?"),
    ("price", "Сколько сейчас стоит iPhone 15 в России?"),
    ("news", "Какие последние новости по космическим запускам?"),
    ("official", "Найди официальную документацию OpenAI Responses API."),
    ("comparison", "Сравни два актуальных варианта облачного хранения для команды."),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--base-url", default=os.getenv("ALTER_BASE_URL", "https://api.alterai.ru"))
    parser.add_argument("--confirm-cost", action="store_true")
    args = parser.parse_args()
    if not args.confirm_cost:
        raise SystemExit("refusing to spend credits; pass --confirm-cost explicitly")
    token = os.getenv("AUTH_TOKEN", "").strip()
    if not token:
        raise SystemExit("AUTH_TOKEN is required")

    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream", "Content-Type": "application/json"}
    records = []
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        for case_id, prompt in CASES:
            started = time.perf_counter()
            status = None
            first_token_ms = None
            chunks = []
            statuses = []
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
                            if first_token_ms is None:
                                first_token_ms = round((time.perf_counter() - started) * 1000, 1)
                            chunks.append(str(payload.get("text") or ""))
                        elif payload.get("type") == "error":
                            error = "stream_error"
            except httpx.HTTPError as exc:
                error = exc.__class__.__name__
            reply = "".join(chunks)
            records.append({
                "case_id": case_id,
                "status": status,
                "first_token_ms": first_token_ms,
                "total_ms": round((time.perf_counter() - started) * 1000, 1),
                "status_sequence": statuses,
                "reply_chars": len(reply),
                "source_links": len(re.findall(r"https?://\S+", reply)),
                "error": error,
            })
    successful = [item for item in records if item["status"] == 200 and not item["error"]]
    result = {"cases": len(records), "successful": len(successful), "records": records}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(records), "successful": len(successful)}, ensure_ascii=False))
    raise SystemExit(0 if len(successful) == len(records) else 1)


if __name__ == "__main__":
    main()
