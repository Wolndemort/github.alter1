"""Offline contract helpers for the Russian quality suite."""

import json
from pathlib import Path

from utils.request_routing import classify_request
from utils.quality import assess_reply, has_language_mismatch


def load_russian_suite(path: str | Path | None = None) -> list[dict]:
    source = Path(path or Path(__file__).parents[1] / "evals" / "russian_v1.json")
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("eval suite must be a list")
    return value


def validate_case(case: dict) -> list[str]:
    errors = []
    for key in ("id", "category", "prompt", "route", "language"):
        if not isinstance(case.get(key), str) or not case[key].strip():
            errors.append(f"missing_{key}")
    if case.get("language") not in {"ru", "en"}:
        errors.append("invalid_language")
    if case.get("route") not in {"chat", "planning", "web", "youtube"}:
        errors.append("invalid_route")
    return errors


def route_accuracy(cases: list[dict] | None = None) -> dict[str, float | int]:
    cases = cases or load_russian_suite()
    valid = [case for case in cases if not validate_case(case)]
    matched = sum(classify_request(case["prompt"]).kind == case["route"] for case in valid)
    return {"total": len(valid), "matched": matched, "accuracy": round(matched / len(valid), 3) if valid else 0.0}


def score_response(case: dict, response: str) -> dict[str, object]:
    """Cheap deterministic gate used before expensive human/model judging."""
    text = str(response or "").strip()
    issues = []
    if not text:
        issues.append("empty")
    if has_language_mismatch(text, case.get("prompt", "")):
        issues.append("language_mismatch")
    quality = assess_reply(text, has_sources=case.get("route") in {"web", "youtube"})
    issues.extend(item for item in quality.issues if item not in issues)
    score = max(0, quality.score - (30 if "empty" in issues else 0))
    blocking = {"empty", "internal_details", "language_mismatch"}
    if case.get("route") in {"web", "youtube"}:
        blocking.add("missing_source_attribution")
    return {"score": score, "issues": tuple(issues), "passed": score >= 70 and not blocking.intersection(issues)}


def summarize_scores(scores: list[dict]) -> dict[str, float | int]:
    """Stable machine-readable summary for ALTER/ChatGPT/Gemini comparisons."""
    if not scores:
        return {"total": 0, "passed": 0, "pass_rate": 0.0, "mean_score": 0.0}
    passed = sum(bool(item.get("passed")) for item in scores)
    mean = sum(float(item.get("score", 0)) for item in scores) / len(scores)
    return {"total": len(scores), "passed": passed, "pass_rate": round(passed / len(scores), 3), "mean_score": round(mean, 1)}
