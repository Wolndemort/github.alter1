import json
from pathlib import Path


def test_capability_suite_has_unique_safe_contract_cases():
    cases = json.loads((Path(__file__).parents[1] / "evals" / "capabilities_v1.json").read_text(encoding="utf-8"))
    assert len(cases) == 20
    assert len({case["id"] for case in cases}) == len(cases)
    assert all(case["cost"] >= 0 for case in cases)
    assert {case["kind"] for case in cases} >= {"memory", "calendar", "audio", "media", "web"}
