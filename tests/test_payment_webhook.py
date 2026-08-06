import pytest
from types import SimpleNamespace

from utils import payment_webhook


class Result:
    def __init__(self, value): self.value = value
    def scalar_one_or_none(self): return self.value


class Db:
    def __init__(self, payment, user=None): self.payment, self.user, self.commits = payment, user, 0
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def execute(self, statement): return Result(self.payment)
    async def get(self, model, user_id, **kwargs): return self.user
    async def commit(self): self.commits += 1


class Request:
    def __init__(self, payload=None, error=None): self.payload, self.error = payload, error
    async def json(self):
        if self.error: raise self.error
        return self.payload


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_json():
    response = await payment_webhook.handle_yookassa_webhook(Request(error=ValueError()))
    assert response.status == 400


@pytest.mark.asyncio
async def test_webhook_ignores_unknown_events_and_missing_ids():
    missing = await payment_webhook.handle_yookassa_webhook(Request({"event": "payment.succeeded", "object": {}}))
    unknown = await payment_webhook.handle_yookassa_webhook(Request({"event": "payment.waiting", "object": {"id": "p1"}}))
    assert 'missing_payment_id' in missing.text
    assert 'payment.waiting' in unknown.text


@pytest.mark.asyncio
async def test_webhook_activates_successful_payment(monkeypatch):
    payment = SimpleNamespace(provider_payment_id="p1", idempotence_key="key", status="pending")
    monkeypatch.setattr(payment_webhook, "async_session", lambda: Db(payment))
    activated = []
    async def activate(session, key): activated.append(key); return True
    monkeypatch.setattr(payment_webhook, "check_and_activate", activate)
    response = await payment_webhook.handle_yookassa_webhook(Request({"event": "payment.succeeded", "object": {"id": "p1"}}))
    assert response.status == 200 and activated == ["key"]


@pytest.mark.asyncio
async def test_webhook_cancels_recurring_payment_and_disables_auto_renew():
    payment = SimpleNamespace(provider_payment_id="p1", idempotence_key="alter-renew-5-day", status="pending", user_id=5)
    user = SimpleNamespace(auto_renew=True)
    db = Db(payment, user)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(payment_webhook, "async_session", lambda: db)
    try:
        response = await payment_webhook.handle_yookassa_webhook(Request({"event": "payment.canceled", "object": {"id": "p1"}}))
    finally:
        monkeypatch.undo()
    assert response.status == 200
    assert payment.status == "canceled" and not user.auto_renew and db.commits == 1
