from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from services import agent_tools


class Result:
    def __init__(self, values): self.values = values
    def scalars(self): return self
    def all(self): return self.values


class Db:
    def __init__(self): self.added = []
    def add(self, value): self.added.append(value)
    async def execute(self, statement): return Result(self.added)


@pytest.mark.asyncio
async def test_agent_reminder_requires_explicit_external_action_permission():
    db = Db(); user = SimpleNamespace(id=7)
    result = await agent_tools.execute_agent_tool("agent_create_reminder", {"text": "call", "remind_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}, db=db, user=user)
    assert result["status"] == "blocked"
    assert db.added == []


@pytest.mark.asyncio
async def test_agent_can_create_future_reminder_when_allowed():
    db = Db(); user = SimpleNamespace(id=7)
    result = await agent_tools.execute_agent_tool("agent_create_reminder", {"text": "call", "remind_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}, db=db, user=user, allow_external_actions=True)
    assert result["status"] == "done"
    assert db.added[0].text == "call"


@pytest.mark.asyncio
async def test_agent_search_tool_delegates_to_existing_safe_tool(monkeypatch):
    async def fake(name, arguments):
        assert name == "web_search"
        return [{"title": "source", "url": "https://example.com"}]
    monkeypatch.setattr(agent_tools, "execute_tool", fake)
    result = await agent_tools.execute_agent_tool("web_search", {"query": "test"}, db=Db(), user=SimpleNamespace(id=7))
    assert result[0]["url"] == "https://example.com"
