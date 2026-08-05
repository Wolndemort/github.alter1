import pytest
from types import SimpleNamespace
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
async def test_guard_does_not_block_when_redis_is_read_only():
    middleware = GuardMiddleware(ReadOnlyRedis())
    seen = []

    async def handler(event, data):
        seen.append(data.copy())

    event = SimpleNamespace(from_user=SimpleNamespace(id=7))
    await middleware(handler, event, {})
    assert seen[0]["billing_allowed"] is True
    assert seen[0]["spam_allowed"] is True

@pytest.mark.asyncio
async def test_guard_sets_spam_flag():
    redis = Redis(); middleware = GuardMiddleware(redis, spam_limit=1, spam_window=3); seen = []
    async def handler(event, data): seen.append(data.copy())
    event = SimpleNamespace(from_user=SimpleNamespace(id=7))
    await middleware(handler, event, {}); await middleware(handler, event, {})
    assert seen[0]["spam_allowed"] is True and seen[1]["spam_allowed"] is False
