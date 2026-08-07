from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from data.models import User, WebAccount
from utils import tasks


class StopLoop(Exception):
    pass


class Result:
    def __init__(self, values=None, value=None): self.values, self.value = values or [], value
    def scalars(self): return self
    def all(self): return self.values
    def scalar_one_or_none(self): return self.value


class Context:
    def __init__(self, db): self.db = db
    async def __aenter__(self): return self.db
    async def __aexit__(self, *args): pass


class Db:
    def __init__(self, values=None): self.values, self.commits, self.rollbacks = values or [], 0, 0
    async def execute(self, statement): return Result(self.values)
    async def commit(self): self.commits += 1
    async def rollback(self): self.rollbacks += 1
    async def get(self, model, user_id, **kwargs):
        return next((item for item in self.values if getattr(item, "id", None) == user_id), None)


def test_telegram_chat_id_never_uses_app_database_id():
    app_only = User(id=101, first_name="App", memory={}, tech_stack={})
    app_only.web_account = WebAccount(
        id="account", user_id=101, email="app@example.com", password_hash="hash"
    )
    assert tasks.telegram_chat_id(app_only) is None

    linked = User(id=101, first_name="App", memory={}, tech_stack={})
    linked.web_account = WebAccount(
        id="account", user_id=101, email="app@example.com", password_hash="hash",
        telegram_user_id=777,
    )
    assert tasks.telegram_chat_id(linked) == 777

    legacy = User(id=777, first_name="Telegram", memory={}, tech_stack={})
    assert tasks.telegram_chat_id(legacy) == 777


@pytest.mark.asyncio
async def test_memory_cleanup_monitor_purges_and_sleeps(monkeypatch):
    db = Db()
    monkeypatch.setattr(tasks, "async_session", lambda: Context(db))
    purged = []
    async def purge(session): purged.append(session); return 4
    async def stop(seconds): raise StopLoop()
    monkeypatch.setattr(tasks, "purge_expired", purge)
    monkeypatch.setattr(tasks.asyncio, "sleep", stop)
    with pytest.raises(StopLoop): await tasks.monitor_memory_cleanup()
    assert purged == [db]


@pytest.mark.asyncio
async def test_personality_monitor_processes_sessions(monkeypatch):
    db = Db(values=[])
    monkeypatch.setattr(tasks, "async_session", lambda: Context(db))
    processed = []
    async def process(session, session_db): processed.append(session); return True
    async def stop(seconds): raise StopLoop()
    monkeypatch.setattr(tasks, "process_session", process)
    monkeypatch.setattr(tasks.asyncio, "sleep", stop)
    with pytest.raises(StopLoop): await tasks.monitor_personality_imprint()
    assert processed == [] and db.commits == 0


@pytest.mark.asyncio
async def test_subscription_renewal_monitor_notifies_success_and_failure(monkeypatch):
    success = User(id=1, first_name="A", memory={}, tech_stack={})
    success.auto_renew = True; success.payment_method_id = "card"; success.next_charge_at = datetime.now(timezone.utc)
    failed = User(id=2, first_name="B", memory={}, tech_stack={})
    failed.auto_renew = True; failed.payment_method_id = "card"; failed.next_charge_at = datetime.now(timezone.utc)
    db = Db([success, failed])
    monkeypatch.setattr(tasks, "async_session", lambda: Context(db))
    async def charge(session, user): return "succeeded" if user.id == 1 else "failed"
    async def stop(seconds): raise StopLoop()
    monkeypatch.setattr(tasks, "charge_recurring_payment", charge)
    monkeypatch.setattr(tasks.asyncio, "sleep", stop)
    sent = []
    bot = SimpleNamespace(send_message=lambda user_id, text: sent.append((user_id, text)))
    async def send(user_id, text): sent.append((user_id, text))
    bot.send_message = send
    with pytest.raises(StopLoop): await tasks.monitor_subscription_renewals(bot)
    assert [item[0] for item in sent] == [1, 2]
    assert db.commits == 1


@pytest.mark.asyncio
async def test_expiry_monitor_sends_once_and_marks_expiry(monkeypatch):
    user = User(id=3, first_name="A", memory={}, tech_stack={})
    user.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=5)
    user.subscription_reminders = {}
    db = Db([user])
    monkeypatch.setattr(tasks, "async_session", lambda: Context(db))
    async def payment(session, current, username, method): return "https://pay.example"
    async def stop(seconds): raise StopLoop()
    monkeypatch.setattr(tasks, "create_payment", payment)
    monkeypatch.setattr(tasks.asyncio, "sleep", stop)
    sent = []
    class Bot:
        async def get_me(self): return SimpleNamespace(username="alter_bot")
        async def send_message(self, user_id, text, **kwargs): sent.append((user_id, text, kwargs))
    with pytest.raises(StopLoop): await tasks.monitor_subscription_expiry_reminders(Bot())
    assert sent and sent[0][0] == 3
    assert user.subscription_reminders
    assert db.commits == 1
