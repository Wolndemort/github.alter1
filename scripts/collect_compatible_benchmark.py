#!/usr/bin/env python3
"""Collect benchmark responses from an OpenAI-compatible model API.

Environment: MODEL_API_KEY, MODEL_NAME, optionally MODEL_BASE_URL and MODEL_ID.
No key is printed or written to the output. A cost confirmation is required.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parents[1]))
from utils.eval_suite import load_russian_suite


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default=os.getenv("MODEL_NAME", ""))
    parser.add_argument("--model-id", default=os.getenv("MODEL_ID", "compatible"))
    parser.add_argument("--base-url", default=os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--confirm-cost", action="store_true")
    args = parser.parse_args()
    key = os.getenv("MODEL_API_KEY", "").strip()
    if not key or not args.model:
        raise SystemExit("MODEL_API_KEY and --model/MODEL_NAME are required")
    if not args.confirm_cost:
        raise SystemExit("refusing to spend money; pass --confirm-cost explicitly")
    cases = load_russian_suite()[: max(1, min(args.limit, 100))]
    records = []
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=90.0) as client:
        for case in cases:
            started = time.perf_counter()
            try:
                response = client.post(
                    f"{args.base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json={"model": args.model, "messages": [{"role": "user", "content": case["prompt"]}], "temperature": 0},
                )
                response.raise_for_status()
                payload = response.json()
                answer = str(payload.get("choices", [{}])[0].get("message", {}).get("content") or "")
                records.append({"model": args.model_id, "case_id": case["id"], "response": answer, "latency_ms": round((time.perf_counter() - started) * 1000, 1)})
            except (httpx.HTTPError, ValueError, IndexError, AttributeError):
                records.append({"model": args.model_id, "case_id": case["id"], "response": "", "latency_ms": round((time.perf_counter() - started) * 1000, 1), "error": "provider_error"})
    args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"collected={len(records)} model={args.model_id} output={args.output}")


if __name__ == "__main__":
    main()
