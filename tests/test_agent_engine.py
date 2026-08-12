from datetime import datetime, timezone

from utils.agent_engine import (
    agent_view,
    block_task,
    claim_next_task,
    complete_task,
    next_ready_task,
    replan_agent,
    start_agent,
)


NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def test_agent_supports_arbitrary_horizon_and_dependency_graph():
    settings = start_agent({}, "Подготовить диету", horizon_minutes=90, tasks=[
        {"id": "goals", "title": "Определить калории", "priority": 1},
        {"id": "menu", "title": "Составить меню", "depends_on": ["goals"]},
        {"id": "shopping", "title": "Собрать список покупок", "depends_on": ["menu"]},
    ], now=NOW)
    assert agent_view(settings)["horizon_minutes"] == 90
    assert next_ready_task(settings)["id"] == "goals"
    settings = claim_next_task(settings, now=NOW)
    settings = complete_task(settings, "goals", "2000 ккал", now=NOW)
    assert next_ready_task(settings)["id"] == "menu"


def test_agent_blocks_and_replans_without_losing_completed_work():
    settings = start_agent({}, "Запустить проект", tasks=[
        {"id": "a", "title": "Собрать данные"},
        {"id": "b", "title": "Сделать запуск", "depends_on": ["a"]},
    ], now=NOW)
    settings = complete_task(settings, "a", "данные собраны", now=NOW)
    settings = block_task(settings, "b", "нет доступа", now=NOW)
    settings = replan_agent(settings, [
        {"id": "a", "title": "Собрать данные"},
        {"id": "c", "title": "Запросить доступ", "depends_on": ["a"]},
        {"id": "b", "title": "Сделать запуск", "depends_on": ["c"]},
    ], reason="появился блокер", now=NOW)
    view = agent_view(settings)
    assert view["tasks"][0]["status"] == "done"
    assert view["next_task"]["id"] == "c"


def test_agent_finishes_after_all_tasks_are_done():
    settings = start_agent({}, "Короткая задача", tasks=[{"id": "one", "title": "Сделать"}], now=NOW)
    settings = complete_task(settings, "one", "готово", now=NOW)
    assert agent_view(settings)["status"] == "completed"
