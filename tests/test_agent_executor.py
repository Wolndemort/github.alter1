import pytest

from services.agent_executor import run_agent_step, run_agent_steps
from utils.agent_engine import agent_view, start_agent


@pytest.mark.asyncio
async def test_executor_completes_ready_tasks_and_preserves_result():
    settings = start_agent({}, "Сделать задачу", tasks=[{"id": "one", "title": "Первый шаг"}])

    async def execute(task, state):
        assert task["id"] == "one"
        assert state["goal"] == "Сделать задачу"
        return "готово"

    settings, task = await run_agent_step(settings, execute)
    assert task["id"] == "one"
    assert agent_view(settings)["status"] == "completed"
    assert agent_view(settings)["tasks"][0]["result"] == "готово"


@pytest.mark.asyncio
async def test_executor_blocks_failed_task_and_does_not_spin():
    settings = start_agent({}, "Сделать задачу", tasks=[{"id": "one", "title": "Первый шаг"}, {"id": "two", "title": "Второй", "depends_on": ["one"]}])
    calls = 0

    async def execute(task, state):
        nonlocal calls
        calls += 1
        raise RuntimeError("provider down")

    settings = await run_agent_steps(settings, execute, max_steps=8)
    view = agent_view(settings)
    assert calls == 1
    assert view["status"] == "blocked"
    assert view["tasks"][0]["status"] == "blocked"
