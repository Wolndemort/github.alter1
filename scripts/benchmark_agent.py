#!/usr/bin/env python3
"""Local zero-credit benchmark for durable agent state transitions."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from utils.agent_engine import claim_next_task, complete_task, replan_agent, start_agent


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return round(ordered[index], 4)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("agent_benchmark.json"))
    parser.add_argument("--runs", type=int, default=1000)
    args = parser.parse_args()
    timings = {"plan": [], "claim": [], "complete": [], "replan": []}
    for _ in range(max(1, args.runs)):
        tasks = [{"id": f"task_{i}", "title": f"Шаг {i}", "depends_on": [f"task_{i - 1}"] if i else []} for i in range(12)]
        started = time.perf_counter(); settings = start_agent({}, "Локальный benchmark", horizon_minutes=60 * 24 * 7, tasks=tasks); timings["plan"].append((time.perf_counter() - started) * 1000)
        started = time.perf_counter(); settings = claim_next_task(settings); timings["claim"].append((time.perf_counter() - started) * 1000)
        started = time.perf_counter(); settings = complete_task(settings, "task_0", "done"); timings["complete"].append((time.perf_counter() - started) * 1000)
        started = time.perf_counter(); replan_agent(settings, tasks + [{"id": "extra", "title": "Новый шаг", "depends_on": ["task_11"]}], "benchmark"); timings["replan"].append((time.perf_counter() - started) * 1000)
    report = {"runs": max(1, args.runs), "operations": {name: {"p50_ms": percentile(values, .50), "p95_ms": percentile(values, .95), "mean_ms": round(statistics.mean(values), 4)} for name, values in timings.items()}}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
