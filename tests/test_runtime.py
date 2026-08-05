import asyncio

from utils.runtime import check_dependencies


def run(coro):
    return asyncio.run(coro)


class FakeRedis:
    def __init__(self, error=None):
        self.error = error

    async def ping(self):
        if self.error:
            raise self.error


class FakeConnection:
    async def execute(self, query):
        return 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeEngine:
    def __init__(self, error=None):
        self.error = error

    def connect(self):
        if self.error:
            return BrokenConnection(self.error)
        return FakeConnection()


class BrokenConnection:
    def __init__(self, error):
        self.error = error

    async def __aenter__(self):
        raise self.error

    async def __aexit__(self, *args):
        return False


def test_dependencies_are_healthy_when_both_services_respond():
    assert run(check_dependencies(FakeRedis(), FakeEngine())) is True


def test_dependencies_fail_gracefully_when_redis_is_down():
    assert run(check_dependencies(FakeRedis(ConnectionError("redis down")), FakeEngine())) is False


def test_dependencies_fail_gracefully_when_postgres_is_down():
    assert run(check_dependencies(FakeRedis(), FakeEngine(ConnectionError("db down")))) is False
