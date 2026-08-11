from pathlib import Path


def test_latency_probe_requires_cost_confirmation_and_does_not_save_replies():
    source = (Path(__file__).parents[1] / "scripts" / "collect_production_latency.py").read_text(encoding="utf-8")
    assert "AUTH_TOKEN" in source
    assert "confirm-cost" in source
    assert "response" not in source.split("records.append", 1)[1]
