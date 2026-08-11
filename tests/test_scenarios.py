from utils.scenarios import get_scenario, list_scenarios


def test_named_scenarios_expose_workflow_presets():
    items = list_scenarios()
    assert len(items) == 7
    assert all(item["workflow_steps"] for item in items)
    assert get_scenario("decision")["workflow_steps"][-1] == "Выбрать решение и первый шаг"


def test_unknown_scenario_is_not_accepted_as_preset():
    assert get_scenario("unknown") is None
