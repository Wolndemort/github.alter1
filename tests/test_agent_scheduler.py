from datetime import datetime, timezone

import pytest

from data.models import User
from utils import tasks
from utils.agent_engine import complete_task, start_agent


NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_autonomous_agent_requires_explicit_opt_in(monkeypatch):
    user = User(id=7, first_name="Test", tech_stack={})
    called = False

    async def run(*args, **kwargs):
        nonlocal called
        called = True
        return user.tech_stack

    monkeypatch.setattr(tasks, "run_agent_steps", run)
    assert await tasks.process_autonomous_agent(user, now=NOW) is False
    assert called is False


@pytest.mark.asyncio
async def test_autonomous_agent_runs_one_due_step_and_schedules_next(monkeypatch):
    user = User(id=7, first_name="Test", tech_stack={})
    user.tech_stack = start_agent({}, "План", tasks=[{"id": "one", "title": "Шаг"}], autonomy_enabled=True, check_interval_minutes=30, now=NOW)

    async def run(settings, executor, max_steps):
        assert max_steps == 1
        return complete_task(settings, "one", "готово", now=NOW)

    monkeypatch.setattr(tasks, "run_agent_steps", run)
    assert await tasks.process_autonomous_agent(user, now=NOW) is True
    assert user.tech_stack["active_agent"]["status"] == "completed"

