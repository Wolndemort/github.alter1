import asyncio

from utils.idempotency import acquire
from utils.redis_store import charge_credits, credits_used, refund_credits


class AtomicRedis:
    def __init__(self):
        self.values = {}
        self.lock = asyncio.Lock()

    async def set(self, key, value, ex=None, nx=False):
        async with self.lock:
            if nx and key in self.values:
                return False
            self.values[key] = value
            return True

    async def get(self, key):
        async with self.lock:
            return self.values.get(key)

    async def incrby(self, key, amount):
        async with self.lock:
            self.values[key] = int(self.values.get(key, 0)) + amount
            return self.values[key]

    async def decrby(self, key, amount):
        async with self.lock:
            self.values[key] = int(self.values.get(key, 0)) - amount
            return self.values[key]

    async def expire(self, key, seconds):
        return True

    async def eval(self, _script, _keys, key, amount):
        async with self.lock:
            value = max(0, int(self.values.get(key, 0)) - int(amount))
            self.values[key] = value
            return value

    async def delete(self, key):
        self.values.pop(key, None)


def test_parallel_idempotency_has_one_winner():
    async def run():
        redis = AtomicRedis()
        results = await asyncio.gather(*(acquire(redis, 7, "/api/v1/media/jobs", "same") for _ in range(40)))
        assert sum(bool(item) for item in results) == 1
    asyncio.run(run())


def test_parallel_quota_respects_limit_and_refund_never_goes_negative():
    async def run():
        redis = AtomicRedis()
        results = await asyncio.gather(*(charge_credits(redis, 7, 1, 10) for _ in range(40)))
        assert sum(results) == 10
        await asyncio.gather(*(refund_credits(redis, 7, 1) for _ in range(40)))
        assert await credits_used(redis, 7) == 0
    asyncio.run(run())
