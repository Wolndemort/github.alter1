#!/usr/bin/env python3
"""Measure production text-stream and voice latency without saving content."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import httpx


TEXT_PROMPTS = (
    "Привет, ответь коротко",
    "Как быстро успокоиться перед важным разговором?",
    "Составь короткий план на сегодня",
)
VOICE_PROMPTS = (
    "Короткий тест голоса.",
    "Озвучь этот ответ быстро.",
)


def percentile(values: list[float], percentile_value: int) -> float:
    """Return a stable nearest-rank percentile for a non-empty sample."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * percentile_value / 100)
    return round(ordered[index], 1)


def summarize(records: list[dict]) -> dict:
    successful = [item for item in records if item.get("status") == 200 and not item.get("error")]
    latencies = [float(item["total_ms"]) for item in successful]
    first_tokens = [float(item["first_token_ms"]) for item in successful if item.get("first_token_ms") is not None]
    result = {
        "total": len(records),
        "successful": len(successful),
        "success_rate": round(len(successful) / len(records), 3) if records else 0.0,
        "total_ms": {
            "mean": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
        },
    }
    if first_tokens:
        result["first_token_ms"] = {
            "mean": round(sum(first_tokens) / len(first_tokens), 1),
            "p50": percentile(first_tokens, 50),
            "p95": percentile(first_tokens, 95),
        }
    return result


def measure_text(client: httpx.Client, base_url: str, headers: dict, prompts: tuple[str, ...], runs: int) -> list[dict]:
    records = []
    for run in range(runs):
        for prompt_index, prompt in enumerate(prompts, 1):
            started = time.perf_counter()
            first_token_ms = None
            statuses = []
            delta_count = 0
            status = None
            error = None
            try:
                with client.stream(
                    "POST",
                    f"{base_url.rstrip('/')}/api/v1/chat/stream",
                    headers=headers,
                    json={"message": prompt},
                ) as response:
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
                            delta_count += 1
                            if first_token_ms is None:
                                first_token_ms = round((time.perf_counter() - started) * 1000, 1)
                        elif payload.get("type") == "error":
                            error = "stream_error"
            except httpx.HTTPError as exc:
                error = exc.__class__.__name__
            records.append({
                "kind": "text",
                "run": run + 1,
                "case": prompt_index,
                "status": status,
                "first_token_ms": first_token_ms,
                "total_ms": round((time.perf_counter() - started) * 1000, 1),
                "delta_count": delta_count,
                "statuses": statuses,
                "error": error,
            })
    return records


def measure_voice(client: httpx.Client, base_url: str, headers: dict, prompts: tuple[str, ...], runs: int) -> list[dict]:
    records = []
    for run in range(runs):
        for prompt_index, prompt in enumerate(prompts, 1):
            started = time.perf_counter()
            status = None
            error = None
            size_bytes = 0
            content_type = None
            try:
                response = client.post(
                    f"{base_url.rstrip('/')}/api/v1/voice/reply",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"text": prompt},
                )
                status = response.status_code
                size_bytes = len(response.content)
                content_type = response.headers.get("content-type")
            except httpx.HTTPError as exc:
                error = exc.__class__.__name__
            records.append({
                "kind": "voice",
                "run": run + 1,
                "case": prompt_index,
                "status": status,
                "total_ms": round((time.perf_counter() - started) * 1000, 1),
                "bytes": size_bytes,
                "content_type": content_type,
                "error": error,
            })
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--base-url", default=os.getenv("ALTER_BASE_URL", "https://api.alterai.ru"))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--text-only", action="store_true")
    parser.add_argument("--voice-only", action="store_true")
    parser.add_argument("--confirm-cost", action="store_true")
    args = parser.parse_args()
    if args.runs < 1 or args.runs > 20:
        raise SystemExit("--runs must be between 1 and 20")
    if args.text_only and args.voice_only:
        raise SystemExit("--text-only and --voice-only are mutually exclusive")
    if not args.confirm_cost:
        raise SystemExit("refusing to spend credits; pass --confirm-cost explicitly")
    token = os.getenv("AUTH_TOKEN", "").strip()
    if not token:
        raise SystemExit("AUTH_TOKEN is required")

    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        text_records = [] if args.voice_only else measure_text(client, args.base_url, headers, TEXT_PROMPTS, args.runs)
        voice_records = [] if args.text_only else measure_voice(client, args.base_url, headers, VOICE_PROMPTS, args.runs)
    report = {
        "base_url": args.base_url.rstrip("/"),
        "runs": args.runs,
        "text": {"summary": summarize(text_records), "records": text_records},
        "voice": {"summary": summarize(voice_records), "records": voice_records},
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"text": report["text"]["summary"], "voice": report["voice"]["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
