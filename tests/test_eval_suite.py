from utils.eval_suite import load_russian_suite, route_accuracy, score_response, summarize_scores, validate_case


def test_russian_eval_suite_has_valid_versioned_contract():
    cases = load_russian_suite()
    assert len(cases) >= 20
    assert all(validate_case(case) == [] for case in cases)
    assert {case["language"] for case in cases} == {"ru", "en"}


def test_russian_eval_route_accuracy_has_a_measurable_baseline():
    result = route_accuracy()
    assert result["total"] >= 20
    assert result["accuracy"] >= 0.75


def test_quality_gate_accepts_russian_answer_and_rejects_internal_leak():
    case = {"prompt": "Составь план", "route": "planning"}
    assert score_response(case, "Вот короткий план из трёх шагов.")["passed"]
    rejected = score_response(case, "We need to answer the user. Let's inspect the prompt.")
    assert not rejected["passed"]
    assert "internal_details" in rejected["issues"]


def test_web_quality_gate_requires_source_attribution():
    result = score_response({"prompt": "Найди актуальную цену", "route": "web"}, "Цена сейчас 100 рублей.")
    assert not result["passed"]
    assert "missing_source_attribution" in result["issues"]


def test_benchmark_summary_is_comparable_between_models():
    summary = summarize_scores([{"score": 100, "passed": True}, {"score": 50, "passed": False}])
    assert summary == {"total": 2, "passed": 1, "pass_rate": 0.5, "mean_score": 75.0}
