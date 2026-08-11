from utils.eval_suite import load_russian_suite, route_accuracy, validate_case


def test_russian_eval_suite_has_valid_versioned_contract():
    cases = load_russian_suite()
    assert len(cases) >= 20
    assert all(validate_case(case) == [] for case in cases)
    assert {case["language"] for case in cases} == {"ru", "en"}


def test_russian_eval_route_accuracy_has_a_measurable_baseline():
    result = route_accuracy()
    assert result["total"] >= 20
    assert result["accuracy"] >= 0.75
