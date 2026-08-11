"""Offline contract helpers for the Russian quality suite."""

import json
from pathlib import Path

from utils.request_routing import classify_request


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
