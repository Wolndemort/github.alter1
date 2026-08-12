import asyncio

from utils.idempotency import acquire, normalize_key, release


class Redis:
    def __init__(self): self.values = {}
    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values: return False
        self.values[key] = (value, ex)
        return True
    async def delete(self, key): self.values.pop(key, None)


def test_idempotency_key_is_normalized_and_bounded():
    assert normalize_key(" request / 1 ") == "request1"
    assert normalize_key(" ") is None


def test_idempotency_acquire_rejects_duplicate_and_release_allows_retry():
    async def run():
        redis = Redis()
        first = await acquire(redis, 7, "youtube_audio", "request-1")
        duplicate = await acquire(redis, 7, "youtube_audio", "request-1")
        assert first and duplicate == ""
        await release(redis, first)
        assert await acquire(redis, 7, "youtube_audio", "request-1")
    asyncio.run(run())
