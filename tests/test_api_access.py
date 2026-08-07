from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from aiohttp import web

from api import chat_routes
from data.models import User


class Db:
    def __init__(self, user): self.user = user
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def get(self, model, user_id): return self.user if self.user and self.user.id == user_id else None


class Request:
    def __init__(self, payload, token="token"):
        self.headers = {"Authorization": f"Bearer {token}"}
        self.payload = payload
    async def json(self): return self.payload


@pytest.mark.asyncio
async def test_chat_route_rejects_unpaid_account(monkeypatch):
    user = User(id=42, first_name="Test", memory={}, tech_stack={})
    monkeypatch.setattr(chat_routes, "async_session", lambda: Db(user))
    monkeypatch.setattr(chat_routes, "_bearer", lambda request: 42)
    with pytest.raises(web.HTTPPaymentRequired):
        await chat_routes.chat_route(Request({"message": "hello"}))


@pytest.mark.asyncio
async def test_chat_route_allows_active_subscription(monkeypatch):
    user = User(id=42, first_name="Test", memory={}, tech_stack={})
    user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    monkeypatch.setattr(chat_routes, "async_session", lambda: Db(user))
    monkeypatch.setattr(chat_routes, "_bearer", lambda request: 42)

    class FakeResult:
        reply = "hello back"
        session_id = 3

    async def reply(self, session, user_id, message):
        assert user_id == 42 and message == "hello"
        return FakeResult()

    monkeypatch.setattr(chat_routes.ChatService, "reply", reply)
    response = await chat_routes.chat_route(Request({"message": "hello"}))
    assert response.status == 200
    assert response.text == '{"reply": "hello back", "session_id": 3}'


@pytest.mark.asyncio
async def test_chat_route_forwards_consented_location(monkeypatch):
    user = User(id=42, first_name="Test", memory={}, tech_stack={})
    user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    monkeypatch.setattr(chat_routes, "async_session", lambda: Db(user))
    monkeypatch.setattr(chat_routes, "_bearer", lambda request: 42)

    class FakeResult:
        reply = "weather back"
        session_id = 4

    async def reply(self, session, user_id, message, location=None):
        assert location == {"city": "Moscow", "region": "Moscow"}
        return FakeResult()

    monkeypatch.setattr(chat_routes.ChatService, "reply", reply)
    response = await chat_routes.chat_route(Request({"message": "погода", "location": {"city": "Moscow", "region": "Moscow"}}))
    assert response.status == 200
