import pytest

from data.models import ImportantEvent, MemoryChunk, Payment, Reminder, Session, User, WebAccount
from services.account_linking import _merge_memory, link_telegram_identity


class Result:
    def __init__(self, value): self.value = value
    def scalar_one_or_none(self): return self.value


class SessionDouble:
    def __init__(self, account, target, legacy):
        self.account = account
        self.target = target
        self.legacy = legacy
        self.execute_calls = 0
        self.deleted = None
        self.bulk_deleted = False

    async def execute(self, statement):
        self.execute_calls += 1
        if self.execute_calls == 8:
            self.bulk_deleted = True
            return Result(None)
        if self.execute_calls == 1:
            return Result(self.account)
        if self.execute_calls == 2:
            return Result(None)
        return Result(None)

    async def get(self, model, identity, **kwargs):
        if model is User and identity == self.target.id:
            return self.target
        if model is User and identity == self.legacy.id:
            return self.legacy
        return None

    async def flush(self): pass


def test_merge_memory_deduplicates_lists_and_preserves_categories():
    result = _merge_memory({"goals": ["launch", "launch"], "name": "Adam"}, {"goals": ["learn"]})
    assert result == {"goals": ["learn", "launch"], "name": "Adam"}


@pytest.mark.asyncio
async def test_linking_merges_legacy_telegram_profile():
    target = User(id=10, first_name="Web", memory={"goals": ["launch"]}, tech_stack={})
    legacy = User(id=777, first_name="Telegram", memory={"goals": ["learn"]}, tech_stack={"voice_replies": True})
    account = WebAccount(id="account", user_id=10, email="user@example.com", password_hash="hash")
    db = SessionDouble(account, target, legacy)

    linked = await link_telegram_identity(db, 10, 777, "adam", "Adam")

    assert linked is target
    assert account.telegram_user_id == 777
    assert target.memory["goals"] == ["learn", "launch"]
    assert target.tech_stack == {"voice_replies": True}
    assert db.bulk_deleted
    assert db.execute_calls == 8  # account, existing link, five updates, and legacy delete
