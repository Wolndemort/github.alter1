import pytest

from utils.redis_store import cache_get, cache_set, charge_credits, charge_request, consume_link_token, create_link_token, refund_credits, state_get, state_set


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expirations = {}

    async def get(self, key): return self.values.get(key)
    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.expirations[key] = ex
        return True
    async def incr(self, key):
        self.values[key] = int(self.values.get(key, 0)) + 1
        return self.values[key]
    async def expire(self, key, seconds): self.expirations[key] = seconds
    async def decr(self, key):
        self.values[key] -= 1
        return self.values[key]
    async def delete(self, key): self.values.pop(key, None)
    async def getdel(self, key): return self.values.pop(key, None)


@pytest.mark.asyncio
async def test_cache_roundtrip():
    redis = FakeRedis()
    await cache_set(redis, "x", "value", ttl=10)
    assert await cache_get(redis, "x") == "value"
    assert redis.expirations["alter:cache:x"] == 10


@pytest.mark.asyncio
async def test_billing_is_limited_and_does_not_overcharge():
    redis = FakeRedis()
    assert await charge_request(redis, 7, 2)
    assert await charge_request(redis, 7, 2)
    assert not await charge_request(redis, 7, 2)
    assert redis.values["alter:billing:7"] == 2


@pytest.mark.asyncio
async def test_credit_billing_supports_redis_without_incrby():
    redis = FakeRedis()
    assert await charge_credits(redis, 7, 2, 3)
    assert not await charge_credits(redis, 7, 2, 3)
    key = next(k for k in redis.values if k.startswith("alter:credits:7:"))
    assert redis.values[key] == 2


@pytest.mark.asyncio
async def test_refund_supports_redis_without_decrby():
    redis = FakeRedis()
    assert await charge_credits(redis, 8, 2, 3)
    assert await refund_credits(redis, 8, 2)
    key = next(k for k in redis.values if k.startswith("alter:credits:8:"))
    assert redis.values[key] == 0


@pytest.mark.asyncio
async def test_state_json_roundtrip():
    redis = FakeRedis()
    await state_set(redis, "session", 7, {"step": "waiting"}, ttl=30)
    assert await state_get(redis, "session", 7) == {"step": "waiting"}


@pytest.mark.asyncio
async def test_telegram_link_token_is_one_time():
    redis = FakeRedis()
    token = await create_link_token(redis, 42, ttl=600)
    assert await consume_link_token(redis, token) == 42
    assert await consume_link_token(redis, token) is None
