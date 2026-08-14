import pytest
from types import SimpleNamespace
from datetime import datetime, timezone
from middleware.guard_middleware import GuardMiddleware

class Redis:
    def __init__(self): self.values = {}; self.expirations = {}
    async def incr(self, key): self.values[key] = int(self.values.get(key, 0)) + 1; return self.values[key]
    async def expire(self, key, seconds): self.expirations[key] = seconds


class ReadOnlyRedis:
    async def incr(self, key):
        from redis.exceptions import ReadOnlyError
        raise ReadOnlyError("read only replica")


@pytest.mark.asyncio
async def test_guard_blocks_when_redis_is_read_only():
    middleware = GuardMiddleware(ReadOnlyRedis())
    seen = []

    async def handler(event, data):
        seen.append(data.copy())

    event = SimpleNamespace(from_user=SimpleNamespace(id=7))
    await middleware(handler, event, {})
    assert seen[0]["billing_allowed"] is False
    assert seen[0]["spam_allowed"] is False

@pytest.mark.asyncio
async def test_guard_sets_spam_flag():
    redis = Redis(); middleware = GuardMiddleware(redis, spam_limit=1, spam_window=3); seen = []
    async def handler(event, data): seen.append(data.copy())
    event = SimpleNamespace(from_user=SimpleNamespace(id=7))
    await middleware(handler, event, {}); await middleware(handler, event, {})
    assert seen[0]["spam_allowed"] is True and seen[1]["spam_allowed"] is False


@pytest.mark.asyncio
async def test_guard_blocks_unpaid_and_reports_to_user(monkeypatch):
    from data.models import User
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    answers = []
    async def answer(text): answers.append(text)
    event = SimpleNamespace(from_user=SimpleNamespace(id=7), text="hello", answer=answer)
    class Db:
        async def get(self, model, ident): return user
    monkeypatch.setattr("middleware.guard_middleware.charge_request", lambda *args: _true())
    monkeypatch.setattr("middleware.guard_middleware.allow_request", lambda *args: _true())
    async def resolved(*args): return user
    async def _true(): return True
    monkeypatch.setattr("middleware.guard_middleware.resolve_telegram_user", resolved)
    monkeypatch.setattr("middleware.guard_middleware.has_active_subscription", lambda _: False)
    seen = []
    async def handler(event, data): seen.append(True)
    await __import__("middleware.guard_middleware", fromlist=["GuardMiddleware"]).GuardMiddleware(object())(handler, event, {"db_session": Db()})
    assert not seen and answers


@pytest.mark.asyncio
async def test_expired_access_blocks_before_consuming_quota_or_mutating_data(monkeypatch):
    from data.models import User
    user = User(id=8, first_name="Adam", memory={"goals": ["ship"]}, tech_stack={}, subscription_reminders={"old": "marker"})
    user.legal_accepted_at = datetime.now(timezone.utc)
    answers = []
    async def answer(text): answers.append(text)
    event = SimpleNamespace(from_user=SimpleNamespace(id=8), text="hello", answer=answer)
    class Db:
        async def get(self, model, ident): return user
    async def resolved(*args): return user
    async def allowed(*args): return True
    charged = []
    async def charge(*args): charged.append(args); return True
    monkeypatch.setattr("middleware.guard_middleware.resolve_telegram_user", resolved)
    monkeypatch.setattr("middleware.guard_middleware.has_active_subscription", lambda _: False)
    monkeypatch.setattr("middleware.guard_middleware.charge_request", allowed)
    monkeypatch.setattr("middleware.guard_middleware.allow_request", allowed)
    monkeypatch.setattr("middleware.guard_middleware.charge_credits", charge)
    await GuardMiddleware(object())(lambda event, data: allowed(), event, {"db_session": Db()})
    assert not charged
    assert user.memory == {"goals": ["ship"]}
    assert user.subscription_reminders == {"old": "marker"}
    assert any("Память, история и настройки сохранены" in text for text in answers)


@pytest.mark.asyncio
async def test_guard_returns_safe_error_when_handler_fails():
    answers = []
    async def answer(text): answers.append(text)
    event = SimpleNamespace(from_user=SimpleNamespace(id=7), answer=answer)
    async def handler(event, data): raise RuntimeError("boom")
    await __import__("middleware.guard_middleware", fromlist=["GuardMiddleware"]).GuardMiddleware(ReadOnlyRedis())(handler, event, {})
    assert answers
