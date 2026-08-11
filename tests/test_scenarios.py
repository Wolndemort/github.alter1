from utils.scenarios import list_scenarios


def test_named_scenarios_are_stable_and_actionable():
    scenarios = list_scenarios()
    assert len(scenarios) == 7
    assert {item["id"] for item in scenarios} == {"my_day", "finish_task", "feelings", "hard_conversation", "decision", "project", "important"}
    assert all(item["prompt"] and item["mode"] for item in scenarios)
