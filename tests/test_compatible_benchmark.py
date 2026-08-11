from pathlib import Path


def test_compatible_benchmark_script_exists_and_documents_cost_guard():
    script = (Path(__file__).parents[1] / "scripts" / "collect_compatible_benchmark.py").read_text(encoding="utf-8")
    assert "MODEL_API_KEY" in script
    assert "confirm-cost" in script
    assert "Authorization" in script
