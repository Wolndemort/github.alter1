from scripts.collect_speed_benchmark import percentile, summarize


def test_percentile_is_stable_for_small_samples():
    assert percentile([100.0, 200.0, 300.0], 50) == 200.0
    assert percentile([], 95) == 0.0


def test_summary_reports_success_rate_and_first_token():
    result = summarize([
        {"status": 200, "error": None, "total_ms": 100, "first_token_ms": 40},
        {"status": 200, "error": None, "total_ms": 200, "first_token_ms": 80},
        {"status": 502, "error": "provider", "total_ms": 300, "first_token_ms": None},
    ])
    assert result["total"] == 3
    assert result["successful"] == 2
    assert result["success_rate"] == round(2 / 3, 3)
    assert result["total_ms"]["p50"] == 100.0
    assert result["first_token_ms"]["p95"] == 80.0
