from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from api import auth_routes
from data.models import User


class Result:
    def __init__(self, value): self.value = value
    def scalar_one_or_none(self): return self.value


class Request:
    def __init__(self, payload=None):
        self.payload = payload or {}
        self.headers = {"Authorization": "Bearer token"}
    async def json(self): return self.payload


class Db:
    def __init__(self, user=None, account=None): self.user, self.account = user, account
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def commit(self): pass
    async def flush(self): pass
    async def get(self, model, user_id, **kwargs): return self.user if self.user and self.user.id == user_id else None
    async def execute(self, statement): return Result(self.account)


@pytest.mark.asyncio
async def test_register_route_returns_verification_required(monkeypatch):
    account = SimpleNamespace(email="user@example.com")
    monkeypatch.setattr(auth_routes, "async_session", lambda: Db())
    async def register(session, email, password): return account
    monkeypatch.setattr(auth_routes, "register", register)
    response = await auth_routes.register_route(Request({"email": "user@example.com", "password": "password123"}))
    assert response.status == 202
    assert response.text == '{"verification_required": true, "email": "user@example.com"}'


@pytest.mark.asyncio
async def test_verify_route_issues_token(monkeypatch):
    account = SimpleNamespace(user_id=9)
    monkeypatch.setattr(auth_routes, "async_session", lambda: Db())
    async def verify(session, email, code): return account
    monkeypatch.setattr(auth_routes, "verify_email", verify)
    monkeypatch.setattr(auth_routes, "_auth_secret", lambda: "secret")
    monkeypatch.setattr(auth_routes, "issue_token", lambda user_id, secret: "access")
    response = await auth_routes.verify_email_route(Request({"email": "user@example.com", "code": "123456"}))
    assert response.status == 200
    assert response.text == '{"access_token": "access", "token_type": "bearer"}'


@pytest.mark.asyncio
async def test_account_memory_and_subscription_routes_share_user(monkeypatch):
    user = User(id=4, first_name="Adam", memory={"goals": ["launch"]}, tech_stack={})
    user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=2)
    account = SimpleNamespace(email="adam@example.com", telegram_user_id=777)
    monkeypatch.setattr(auth_routes, "async_session", lambda: Db(user, account))
    monkeypatch.setattr(auth_routes, "_bearer", lambda request: 4)
    account_response = await auth_routes.account_route(Request())
    memory_response = await auth_routes.memory_route(Request())
    subscription_response = await auth_routes.subscription_route(Request())
    assert '"telegram_linked": true' in account_response.text
    assert '"goals": ["launch"]' in memory_response.text
    assert '"active": true' in subscription_response.text


@pytest.mark.asyncio
async def test_start_link_returns_deep_link(monkeypatch):
    class Redis:
        pass
    monkeypatch.setattr(auth_routes, "_bearer", lambda request: 4)
    monkeypatch.setattr(auth_routes, "create_redis", lambda: Redis())
    async def create_link(redis, user_id): return "one-time"
    async def close(redis): pass
    monkeypatch.setattr(auth_routes, "create_link_token", create_link)
    monkeypatch.setattr(auth_routes, "close_redis", close)
    response = await auth_routes.start_telegram_link_route(Request())
    assert "start=link_one-time" in response.text
