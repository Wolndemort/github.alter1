#!/usr/bin/env python3
"""Collect ALTER production responses for the offline benchmark scorer.

Requires AUTH_TOKEN and an explicit --confirm-cost because each case spends a
normal chat credit. The token is never printed or written to the output.
"""

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parents[1]))

from utils.benchmark import parse_sse_stream
from utils.eval_suite import load_russian_suite


def select_cases(cases: list[dict], case_ids: list[str], limit: int) -> list[dict]:
    if case_ids:
        wanted = set(case_ids)
        cases = [case for case in cases if case["id"] in wanted]
    return cases[: max(1, min(limit, 100))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--case-id", action="append", dest="case_ids", default=[], help="run selected case id(s) only")
    parser.add_argument("--confirm-cost", action="store_true")
    parser.add_argument("--base-url", default=os.getenv("ALTER_BASE_URL", "https://api.alterai.ru"))
    args = parser.parse_args()
    token = os.getenv("AUTH_TOKEN", "").strip()
    if not token:
        raise SystemExit("AUTH_TOKEN is required")
    if not args.confirm_cost:
        raise SystemExit("refusing to spend credits; pass --confirm-cost explicitly")
    cases = select_cases(load_russian_suite(), args.case_ids, args.limit)
    records = []
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream", "Content-Type": "application/json"}
    with httpx.Client(timeout=90.0, follow_redirects=True) as client:
        for case in cases:
            started = time.perf_counter()
            try:
                response = client.post(f"{args.base_url.rstrip('/')}/api/v1/chat/stream", headers=headers, json={"message": case["prompt"]})
                response.raise_for_status()
                answer, statuses, stream_error = parse_sse_stream(response.text)
                records.append({"model": "alter", "case_id": case["id"], "response": answer, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "statuses": statuses, "error": stream_error})
            except httpx.HTTPError:
                records.append({"model": "alter", "case_id": case["id"], "response": "", "latency_ms": round((time.perf_counter() - started) * 1000, 1), "error": "http_error"})
    args.output.write_text(__import__("json").dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"collected={len(records)} output={args.output}")


if __name__ == "__main__":
    main()
