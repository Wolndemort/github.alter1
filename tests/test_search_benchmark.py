from scripts.collect_search_benchmark import CASES


def test_search_benchmark_covers_core_freshness_and_local_scenarios():
    case_ids = {case_id for case_id, _ in CASES}
    assert {"local", "open_now", "price", "news", "official", "comparison"} <= case_ids
    assert len(CASES) == len(case_ids)
