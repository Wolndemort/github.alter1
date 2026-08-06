from types import SimpleNamespace

import pytest

from middleware.billing_middleware import BillingMiddleware
from middleware.db_middleware import DbSessionMiddleware


@pytest.mark.asyncio
async def test_billing_middleware_charges_user_and_passes_data(monkeypatch):
    calls = []
    async def charge(redis, user_id, limit):
        calls.append((redis, user_id, limit)); return False
    monkeypatch.setattr("middleware.billing_middleware.charge_request", charge)
    seen = []
    async def handler(event, data): seen.append(data.copy()); return "ok"
    result = await BillingMiddleware("redis")(handler, SimpleNamespace(from_user=SimpleNamespace(id=8)), {})
    assert result == "ok" and calls[0][1] == 8 and seen[0]["billing_allowed"] is False


@pytest.mark.asyncio
async def test_billing_middleware_handles_events_without_user():
    seen = []
    async def handler(event, data): seen.append(data); return "ok"
    assert await BillingMiddleware("redis")(handler, SimpleNamespace(), {}) == "ok"
    assert seen == [{}]


@pytest.mark.asyncio
async def test_db_middleware_scopes_session_and_injects_it():
    class Context:
        async def __aenter__(self): return "db-session"
        async def __aexit__(self, *args): pass
    seen = []
    async def handler(event, data): seen.append(data["db_session"]); return "ok"
    assert await DbSessionMiddleware(lambda: Context())(handler, object(), {}) == "ok"
    assert seen == ["db-session"]
