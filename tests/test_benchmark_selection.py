from scripts.collect_alter_benchmark import select_cases


def test_benchmark_can_select_only_failed_case_ids():
    cases = [{"id": "ok"}, {"id": "failed"}, {"id": "other"}]
    assert select_cases(cases, ["failed"], 20) == [{"id": "failed"}]
