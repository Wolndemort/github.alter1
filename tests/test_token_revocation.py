import asyncio

from utils.redis_store import is_token_revoked, revoke_token


class Redis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, ex=None):
        self.values[key] = (value, ex)

    async def get(self, key):
        return self.values.get(key, (None, None))[0]


def test_token_revocation_is_scoped_and_detectable():
    async def run():
        redis = Redis()
        assert not await is_token_revoked(redis, "token-a")
        await revoke_token(redis, "token-a")
        assert await is_token_revoked(redis, "token-a")
        assert not await is_token_revoked(redis, "token-b")
    asyncio.run(run())
