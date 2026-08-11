from datetime import datetime, timedelta, timezone
import pytest
from aiohttp import web
from api import user_features_routes as routes
from data.models import User

class Request:
    def __init__(self, payload=None, reminder_id=None): self.payload = payload or {}; self.match_info = {"reminder_id": str(reminder_id)}
    async def json(self): return self.payload

class Result:
    def __init__(self, values=None, value=None): self.values, self.value = values or [], value
    def scalars(self): return self
    def all(self): return self.values
    def scalar_one_or_none(self): return self.value

class Db:
    def __init__(self, user): self.user, self.added, self.deleted, self.commits = user, [], [], 0
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def get(self, model, ident): return self.user if ident == self.user.id else None
    async def execute(self, statement): return Result(self.added, self.added[0] if self.added else None)
    def add(self, value): value.id = 1; self.added.append(value)
    async def delete(self, value): self.deleted.append(value)
    async def commit(self): self.commits += 1

@pytest.fixture
def user():
    return User(id=7, first_name="Test", memory={}, tech_stack={})

@pytest.mark.asyncio
async def test_settings_and_checkins_update(monkeypatch, user):
    db = Db(user); monkeypatch.setattr(routes, "async_session", lambda: db); monkeypatch.setattr(routes, "_bearer", lambda request: 7)
    response = await routes.update_settings_route(Request({"voice_replies": True, "private_mode": True, "quiet_start": 22}))
    assert response.status == 200 and user.tech_stack["quiet_start"] == 22
    assert user.tech_stack["private_mode"] is True
    response = await routes.checkins_route(Request({"enabled": False}))
    assert response.status == 200 and user.checkins_enabled is False

@pytest.mark.asyncio
async def test_invalid_settings_and_checkins_are_rejected(monkeypatch, user):
    db = Db(user); monkeypatch.setattr(routes, "async_session", lambda: db); monkeypatch.setattr(routes, "_bearer", lambda request: 7)
    with pytest.raises(web.HTTPBadRequest): await routes.update_settings_route(Request({"unknown": True}))
    with pytest.raises(web.HTTPBadRequest): await routes.update_settings_route(Request({"quiet_start": 99}))
    with pytest.raises(web.HTTPBadRequest): await routes.checkins_route(Request({"enabled": "yes"}))


@pytest.mark.asyncio
async def test_push_token_is_validated_and_persisted(monkeypatch, user):
    db = Db(user); monkeypatch.setattr(routes, "async_session", lambda: db); monkeypatch.setattr(routes, "_bearer", lambda request: 7)
    response = await routes.push_token_route(Request({"token": "ExponentPushToken[abc]"}))
    assert response.status == 200
    assert user.tech_stack["expo_push_token"] == "ExponentPushToken[abc]"
    with pytest.raises(web.HTTPBadRequest):
        await routes.push_token_route(Request({"token": "not-a-push-token"}))


@pytest.mark.asyncio
async def test_action_log_and_scenarios_routes_are_safe(monkeypatch, user):
    user.tech_stack = {"_action_log": [{"action": "chat", "status": "ok"}], "private_mode": False}
    db = Db(user); monkeypatch.setattr(routes, "async_session", lambda: db); monkeypatch.setattr(routes, "_bearer", lambda request: 7)
    action_response = await routes.action_log_route(Request())
    assert action_response.status == 200
    scenario_response = await routes.scenarios_route(Request())
    assert scenario_response.status == 200


@pytest.mark.asyncio
async def test_workflow_routes_start_and_advance_goal(monkeypatch, user):
    db = Db(user); monkeypatch.setattr(routes, "async_session", lambda: db); monkeypatch.setattr(routes, "_bearer", lambda request: 7)
    response = await routes.workflow_start_route(Request({"workflow_id": "finish_task", "goal": "Запустить лендинг"}))
    assert response.status == 200
    assert user.tech_stack["active_workflow"]["goal"] == "Запустить лендинг"
    response = await routes.workflow_next_route(Request({}))
    assert response.status == 200
    assert user.tech_stack["active_workflow"]["current_step"] == 1


@pytest.mark.asyncio
async def test_workflow_persistence_is_blocked_in_private_mode(monkeypatch, user):
    user.tech_stack = {"private_mode": True}
    db = Db(user); monkeypatch.setattr(routes, "async_session", lambda: db); monkeypatch.setattr(routes, "_bearer", lambda request: 7)
    with pytest.raises(web.HTTPConflict):
        await routes.workflow_start_route(Request({"goal": "Не сохранять"}))


@pytest.mark.asyncio
async def test_quality_diagnostics_requires_owner_and_returns_dashboard(monkeypatch, user):
    db = Db(user); monkeypatch.setattr(routes, "async_session", lambda: db); monkeypatch.setattr(routes, "_bearer", lambda request: 7)
    monkeypatch.setattr(routes, "has_owner_access", lambda *args: True)
    response = await routes.quality_diagnostics_route(Request())
    assert response.status == 200

@pytest.mark.asyncio
async def test_create_reminder_requires_future_timezone_aware_date(monkeypatch, user):
    db = Db(user); monkeypatch.setattr(routes, "async_session", lambda: db); monkeypatch.setattr(routes, "_bearer", lambda request: 7)
    with pytest.raises(web.HTTPBadRequest): await routes.create_reminder_route(Request({"text": "call", "remind_at": "2026-01-01T10:00:00"}))
    with pytest.raises(web.HTTPBadRequest): await routes.create_reminder_route(Request({"text": "call", "remind_at": "2020-01-01T10:00:00+00:00"}))
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    response = await routes.create_reminder_route(Request({"text": "call", "remind_at": future}))
    assert response.status == 201 and db.added[0].text == "call"
