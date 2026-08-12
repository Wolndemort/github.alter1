from pathlib import Path


def test_quality_benchmark_is_zero_credit_and_deterministic():
    source = (Path(__file__).parents[1] / "scripts" / "quality-benchmark.py").read_text(encoding="utf-8")
    assert "httpx" not in source
    assert "chat_with" not in source
    assert "CAPABILITY_CATALOG" in source
