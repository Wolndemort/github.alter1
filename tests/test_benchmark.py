from utils.benchmark import aggregate_model_reports, score_records


def test_benchmark_scores_and_aggregates_models_comparably():
    cases = {
        "hello": {"id": "hello", "prompt": "Привет", "route": "chat"},
        "web": {"id": "web", "prompt": "Найди цену", "route": "web"},
    }
    scored = score_records(cases, [
        {"model": "alter", "case_id": "hello", "response": "Привет!", "latency_ms": 10},
        {"model": "alter", "case_id": "web", "response": "Цена: 10 рублей.", "latency_ms": 30},
        {"model": "gemini", "case_id": "hello", "response": "Sure, hi!", "latency_ms": 20},
    ])
    reports = aggregate_model_reports(scored)
    assert reports["alter"]["total"] == 2
    assert reports["alter"]["p95_latency_ms"] == 10
    assert "language_mismatch" in reports["gemini"]["issues"]
