import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from config import config
from data.models import Payment, User
from middleware.guard_middleware import GuardMiddleware
from utils import billing
from utils.billing import charge_recurring_payment, check_and_activate, create_payment, has_active_subscription
from utils.keyboards import AUTO_RENEW_OFF_BUTTON, AUTO_RENEW_ON_BUTTON, BUY_SUBSCRIPTION_BUTTON, UNLINK_CARD_BUTTON, cabinet_keyboard


def run(coro):
    return asyncio.run(coro)


class Result:
    def __init__(self, value=None, values=None):
        self.value = value
        self.values = values or []

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.values


class Session:
    def __init__(self, payment=None, user=None):
        self.payment = payment
        self.user = user
        self.added = []
        self.deleted = []
        self.commits = 0

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def delete(self, value):
        self.deleted.append(value)

    async def get(self, model, ident, **kwargs):
        return self.user

    async def execute(self, statement):
        return Result(self.payment)


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class FakeClient:
    response = None
    requests = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, url, **kwargs):
        self.requests.append(("POST", url, kwargs))
        return self.response

    async def get(self, url, **kwargs):
        self.requests.append(("GET", url, kwargs))
        return self.response


@pytest.fixture
def configured_yookassa(monkeypatch):
    monkeypatch.setattr(config, "SUBSCRIPTION_PRICE_RUB", "990.00")
    monkeypatch.setattr(config, "EGO_PRICE_RUB", "2990.00")
    monkeypatch.setattr(config, "YUKASSA_SHOP_ID", "shop-1")
    monkeypatch.setattr(config, "YUKASSA_SECRET_KEY", SimpleNamespace(get_secret_value=lambda: "secret"))
    monkeypatch.setattr(config, "YUKASSA_RECEIPT_EMAIL", None)
    monkeypatch.setattr(config, "YUKASSA_SAVE_PAYMENT_METHOD", True)
    monkeypatch.setattr(billing.httpx, "AsyncClient", FakeClient)
    FakeClient.requests = []


def test_owner_and_price_helpers(monkeypatch):
    monkeypatch.setattr(config, "OWNER_TELEGRAM_IDS", "1271717628, 42, invalid")
    assert billing.owner_ids() == {1271717628, 42}
    assert billing.is_owner(1271717628)
    assert not billing.is_owner(7)
    assert billing.price() > 0


def test_active_subscription_requires_future_expiration():
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    assert not has_active_subscription(user)
    user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    assert has_active_subscription(user)
    user.subscription_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert not has_active_subscription(user)


@pytest.mark.parametrize("method", ["bank_card", "sbp"])
def test_create_payment_builds_card_and_sbp_payloads(monkeypatch, configured_yookassa, method):
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    session = Session(user=user)
    FakeClient.response = FakeResponse(201, {"id": "pay-1", "confirmation": {"confirmation_url": "https://pay"}})
    assert run(create_payment(session, user, "alter_bot", method)) == "https://pay"
    payload = FakeClient.requests[0][2]["json"]
    assert payload["metadata"]["user_id"] == "7"
    if method == "bank_card":
        assert payload["save_payment_method"] is True
        assert "payment_method_data" not in payload
    else:
        assert payload["payment_method_data"] == {"type": "sbp"}
        assert "save_payment_method" not in payload


def test_create_payment_removes_local_payment_when_provider_rejects(configured_yookassa):
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    session = Session(user=user)
    FakeClient.response = FakeResponse(400, {"description": "bad request"})
    with pytest.raises(RuntimeError, match="bad request"):
        run(create_payment(session, user, "alter_bot"))
    assert len(session.deleted) == 1


def test_check_and_activate_verifies_provider_and_saves_card(configured_yookassa):
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    payment = Payment(user_id=7, provider_payment_id="pay-1", idempotence_key="key-1", amount_rub="990.00", status="pending")
    session = Session(payment=payment, user=user)
    FakeClient.response = FakeResponse(200, {
        "status": "succeeded", "paid": True,
        "amount": {"value": "990.00", "currency": "RUB"},
        "metadata": {"payment_key": "key-1", "user_id": "7"},
        "payment_method": {"id": "pm-1"},
    })
    assert run(check_and_activate(session, "key-1")) is True
    assert payment.status == "succeeded"
    assert user.payment_method_id == "pm-1"
    assert has_active_subscription(user)
    assert user.next_charge_at == user.subscription_expires_at


def test_ego_payment_uses_ego_amount_and_persists_plan(configured_yookassa):
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    session = Session(user=user)
    FakeClient.response = FakeResponse(201, {"id": "ego-pay", "confirmation": {"confirmation_url": "https://pay"}})
    assert run(create_payment(session, user, "alter_bot", plan="ego")) == "https://pay"
    payload = FakeClient.requests[0][2]["json"]
    assert payload["amount"]["value"] == "2990.00"
    assert payload["metadata"]["plan"] == "ego"

    payment = session.added[-1]
    session.payment = payment
    payment.provider_payment_id = "ego-pay"
    FakeClient.response = FakeResponse(200, {
        "status": "succeeded", "paid": True,
        "amount": {"value": "2990.00", "currency": "RUB"},
        "metadata": {"payment_key": payment.idempotence_key, "user_id": "7", "plan": "ego"},
    })
    assert run(check_and_activate(session, payment.idempotence_key)) is True
    assert user.tech_stack["subscription_plan"] == "ego"


def test_successful_payment_is_idempotent_after_first_activation(configured_yookassa):
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    payment = Payment(user_id=7, provider_payment_id="pay-1", idempotence_key="key-1", amount_rub="990.00", status="succeeded")
    session = Session(payment=payment, user=user)
    FakeClient.response = FakeResponse(200, {
        "status": "succeeded", "paid": True,
        "amount": {"value": "990.00", "currency": "RUB"},
        "metadata": {"payment_key": "key-1", "user_id": "7"},
    })
    assert run(check_and_activate(session, "key-1")) is True
    assert user.subscription_expires_at is None


@pytest.mark.parametrize("payload", [
    {"status": "pending", "paid": False},
    {"status": "succeeded", "paid": True, "amount": {"value": "1.00", "currency": "RUB"}},
    {"status": "succeeded", "paid": True, "amount": {"value": "990.00", "currency": "RUB"}, "metadata": {"payment_key": "other", "user_id": "7"}},
])
def test_check_and_activate_rejects_unverified_result(configured_yookassa, payload):
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    payment = Payment(user_id=7, provider_payment_id="pay-1", idempotence_key="key-1", amount_rub="990.00", status="pending")
    session = Session(payment=payment, user=user)
    FakeClient.response = FakeResponse(200, payload)
    assert run(check_and_activate(session, "key-1")) is False
    assert payment.status == "pending"
    assert not has_active_subscription(user)


def test_recurring_payment_uses_saved_method_and_extends_subscription(configured_yookassa):
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(seconds=20)
    user.next_charge_at = user.subscription_expires_at
    user.payment_method_id = "pm-1"
    user.auto_renew = True
    session = Session(user=user)
    FakeClient.response = FakeResponse(201, {"id": "renew-1", "status": "succeeded", "payment_method": {"id": "pm-1"}})
    old_expiry = user.subscription_expires_at
    assert run(charge_recurring_payment(session, user)) == "succeeded"
    assert user.subscription_expires_at > old_expiry
    assert session.added and session.added[0].status == "succeeded"
    assert FakeClient.requests[0][2]["json"]["payment_method_id"] == "pm-1"


def test_recurring_failure_disables_auto_renew(configured_yookassa):
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    user.payment_method_id = "pm-1"
    user.auto_renew = True
    user.next_charge_at = datetime.now(timezone.utc)
    session = Session(user=user)
    FakeClient.response = FakeResponse(402, {"description": "declined"})
    assert run(charge_recurring_payment(session, user)) == "failed"
    assert user.auto_renew is False


def test_recurring_pending_waits_for_webhook(configured_yookassa):
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    user.payment_method_id = "pm-1"
    user.auto_renew = True
    user.next_charge_at = datetime.now(timezone.utc)
    session = Session(user=user)
    FakeClient.response = FakeResponse(201, {"id": "renew-pending", "status": "pending"})
    assert run(charge_recurring_payment(session, user)) == "pending"
    assert session.added and session.added[0].status == "pending"
    assert user.next_charge_at > datetime.now(timezone.utc)


def test_recurring_skips_without_opt_in_or_card():
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    assert run(charge_recurring_payment(Session(user=user), user)) == "skipped"


def test_recurring_does_not_charge_same_idempotence_key_twice(configured_yookassa):
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    user.payment_method_id = "pm-1"
    user.auto_renew = True
    user.next_charge_at = datetime.now(timezone.utc)
    existing = Payment(user_id=7, idempotence_key=f"alter-renew-7-{user.next_charge_at.date().isoformat()}", amount_rub="990.00", status="succeeded")
    session = Session(payment=existing, user=user)
    assert run(charge_recurring_payment(session, user)) == "already_paid"
    assert not FakeClient.requests


def test_cabinet_keyboard_reflects_card_and_auto_renew_state():
    labels = [button.text for row in cabinet_keyboard(auto_renew=True, has_card=True).keyboard for button in row]
    assert AUTO_RENEW_OFF_BUTTON in labels
    assert UNLINK_CARD_BUTTON in labels
    assert BUY_SUBSCRIPTION_BUTTON in labels
    labels = [button.text for row in cabinet_keyboard(auto_renew=False, has_card=False).keyboard for button in row]
    assert AUTO_RENEW_ON_BUTTON in labels
    assert UNLINK_CARD_BUTTON not in labels


class Redis:
    def __init__(self):
        self.values = {}

    async def incr(self, key):
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key, seconds):
        pass


class Db:
    def __init__(self, user):
        self.user = user

    async def get(self, model, user_id):
        return self.user


def test_guard_blocks_unpaid_non_exempt_message():
    answers = []
    user = User(id=88, first_name="Test", memory={}, tech_stack={})

    class Event:
        from_user = SimpleNamespace(id=88)
        text = "hello"

        async def answer(self, text):
            answers.append(text)

    seen = []

    async def handler(event, data):
        seen.append(True)

    run(GuardMiddleware(Redis())(handler, Event(), {"db_session": Db(user)}))
    assert not seen
    assert answers and "/start" in answers[0]


def test_guard_allows_billing_command_and_owner(monkeypatch):
    monkeypatch.setattr(config, "OWNER_TELEGRAM_IDS", "1271717628")
    user = User(id=88, first_name="Test", memory={}, tech_stack={})
    user.legal_accepted_at = datetime.now(timezone.utc)
    seen = []

    async def handler(event, data):
        seen.append(data["subscription_allowed"])

    run(GuardMiddleware(Redis())(handler, SimpleNamespace(from_user=SimpleNamespace(id=88), text="/buy"), {"db_session": Db(user)}))
    assert seen == [False]
    run(GuardMiddleware(Redis())(handler, SimpleNamespace(from_user=SimpleNamespace(id=1271717628), text="hello"), {"db_session": Db(user)}))
    assert seen[-1] is True


def test_unconfigured_payment_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "YUKASSA_SHOP_ID", None)
    monkeypatch.setattr(config, "YUKASSA_SECRET_KEY", None)
    user = User(id=7, first_name="Test", memory={}, tech_stack={})
    with pytest.raises(RuntimeError, match="not configured"):
        run(create_payment(Session(user=user), user, "alter_bot"))
