#!/usr/bin/env python3
"""Bounded, non-billing availability load check for health/readiness endpoints."""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx


async def one(client: httpx.AsyncClient, url: str) -> dict:
    started = time.perf_counter()
    try:
        response = await client.get(url)
        return {"status": response.status_code, "ms": (time.perf_counter() - started) * 1000}
    except httpx.HTTPError as exc:
        return {"status": 0, "ms": (time.perf_counter() - started) * 1000, "error": type(exc).__name__}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://api.alterai.ru")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.requests <= 500 or not 1 <= args.concurrency <= 50:
        raise SystemExit("requests must be 1..500 and concurrency 1..50")
    urls = [f"{args.base_url.rstrip('/')}/{name}" for name in ("health", "ready")]
    semaphore = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(timeout=15, limits=httpx.Limits(max_connections=args.concurrency)) as client:
        async def guarded(url):
            async with semaphore:
                return await one(client, url)
        results = await asyncio.gather(*(guarded(urls[index % 2]) for index in range(args.requests)))
    latencies = [item["ms"] for item in results]
    failures = [item for item in results if item["status"] != 200]
    ordered = sorted(latencies)
    percentile = lambda value: ordered[round((len(ordered) - 1) * value / 100)]
    report = {"requests": args.requests, "concurrency": args.concurrency, "success": len(failures) == 0, "failures": len(failures), "p50_ms": round(percentile(50), 1), "p95_ms": round(percentile(95), 1), "max_ms": round(max(latencies), 1), "mean_ms": round(statistics.mean(latencies), 1)}
    print(report)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
