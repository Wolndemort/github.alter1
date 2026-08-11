"""Comparable benchmark report generation for model runs."""

from collections import defaultdict

from utils.eval_suite import score_response


def parse_sse_stream(body: str) -> tuple[str, list[str], str | None]:
    """Parse ALTER's SSE contract without retaining raw event payloads."""
    response = []
    statuses = []
    error = None
    for block in body.split("\n\n"):
        line = next((item[6:] for item in block.splitlines() if item.startswith("data: ")), None)
        if not line:
            continue
        try:
            import json
            payload = json.loads(line)
        except (TypeError, ValueError):
            continue
        if payload.get("type") == "status":
            statuses.append(str(payload.get("status") or ""))
        elif payload.get("type") == "delta":
            response.append(str(payload.get("text") or ""))
        elif payload.get("type") == "error":
            error = "stream_error"
    return "".join(response), statuses, error


def score_records(cases_by_id: dict[str, dict], records: list[dict]) -> list[dict]:
    scored = []
    for record in records:
        case = cases_by_id.get(str(record.get("case_id")))
        if case is None:
            scored.append({**record, "score": 0, "passed": False, "issues": ["unknown_case"]})
            continue
        result = score_response(case, str(record.get("response") or ""))
        scored.append({
            "model": str(record.get("model") or "unknown"),
            "case_id": str(record.get("case_id")),
            "latency_ms": float(record.get("latency_ms") or 0),
            "score": result["score"],
            "passed": result["passed"],
            "issues": list(result["issues"]),
        })
    return scored


def aggregate_model_reports(scored: list[dict]) -> dict[str, dict]:
    grouped = defaultdict(list)
    for record in scored:
        grouped[record["model"]].append(record)
    reports = {}
    for model, records in grouped.items():
        passed = sum(bool(item["passed"]) for item in records)
        latencies = sorted(float(item["latency_ms"]) for item in records)
        issues = defaultdict(int)
        for item in records:
            for issue in item.get("issues", []):
                issues[issue] += 1
        reports[model] = {
            "total": len(records),
            "passed": passed,
            "pass_rate": round(passed / len(records), 3) if records else 0.0,
            "mean_score": round(sum(float(item["score"]) for item in records) / len(records), 1) if records else 0.0,
            "p50_latency_ms": latencies[(len(latencies) - 1) * 50 // 100] if latencies else 0.0,
            "p95_latency_ms": latencies[(len(latencies) - 1) * 95 // 100] if latencies else 0.0,
            "issues": dict(issues),
        }
    return reports
