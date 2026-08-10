from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from api import auth_routes
from data.models import User


class Request:
    headers = {"Authorization": "Bearer token"}


class Result:
    def __init__(self, values): self.values = values
    def scalars(self): return self
    def all(self): return self.values


class Db:
    def __init__(self, user, results): self.user, self.results = user, iter(results)
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def get(self, model, user_id): return self.user
    async def execute(self, statement): return next(self.results)


@pytest.mark.asyncio
async def test_my_day_combines_reminders_loops_goals_and_next_step(monkeypatch):
    user = User(id=7, first_name="Adam", memory={"open_loops": [{"title": "Доделать ALTER"}], "goals_habits": {"goal": "Запустить продукт"}}, tech_stack={})
    reminder = SimpleNamespace(text="Позвонить партнёру", remind_at=datetime.now(timezone.utc) + timedelta(hours=2))
    event = SimpleNamespace(title="Демо", description="Показать продукт", event_type="event", importance="high", occurred_at=datetime.now(timezone.utc))
    monkeypatch.setattr(auth_routes, "_bearer", lambda request: 7)
    monkeypatch.setattr(auth_routes, "async_session", lambda: Db(user, [Result([reminder]), Result([event])]))

    response = await auth_routes.my_day_route(Request())
    assert response.status == 200
    payload = json.loads(response.text)
    assert payload["memory_permanent"] is True
    titles = {item["title"] for item in payload["focus"]}
    assert {"Позвонить партнёру", "Доделать ALTER", "Запустить продукт"} <= titles
