import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from data.models import Session, User
from utils import tasks
from utils.tasks import extract_health_followup, extract_important_events, extract_followups, process_session


def test_extract_important_events_normalizes_model_output():
    result = extract_important_events({"important_events": {"event_type": "career", "title": "Запуск проекта", "importance": "high"}})
    assert result[0]["event_type"] == "career"
    assert result[0]["title"] == "Запуск проекта"


def test_extract_important_events_discards_invalid_items():
    assert extract_important_events({"important_events": [None, {}, "bad"]}) == []


def test_extract_followups_accepts_iso_datetime_and_question():
    result = extract_followups({"open_loops": {
        "title": "тренировка",
        "follow_up_question": "Как прошла тренировка?",
        "follow_up_at": "2026-08-05T19:00:00+03:00",
    }})
    assert len(result) == 1
    assert result[0]["text"] == "Как прошла тренировка?"
    assert result[0]["remind_at"].isoformat() == "2026-08-05T19:00:00+03:00"


def test_extract_followups_ignores_missing_or_invalid_time():
    facts = {"open_loops": [
        {"title": "без времени"},
        {"title": "невалидная дата", "follow_up_at": "завтра"},
        None,
        "bad",
    ]}
    assert extract_followups(facts) == []


def test_extract_health_followup_ignores_negative_health_statements():
    assert extract_health_followup([{"role": "user", "content": "ничего не болит"}]) is None


def test_extract_health_followup_ignores_malformed_message_items():
    assert extract_health_followup([["corrupt"], "also corrupt", {"role": "user", "content": "у меня болит голова"}])


def test_extract_health_followup_creates_utc_reminder():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = extract_health_followup([{"role": "user", "content": "у меня болит голова"}], now)
    assert result and result["remind_at"] == now + timedelta(hours=4)


@pytest.mark.asyncio
async def test_process_session_is_idempotent_for_events_and_followups(monkeypatch):
    user = User(id=5, first_name="Test", memory={}, tech_stack={})
    user.checkins_enabled = False
    session = Session(id=9, user_id=5, raw_messages=[{"role": "user", "content": "Запусти проект"}], user=user)
    db = SimpleNamespace(added=[], commits=0)
    class Result:
        def scalar_one_or_none(self): return None
    async def execute(statement): return Result()
    async def commit(): db.commits += 1
    db.execute = execute; db.commit = commit
    db.add = lambda value: db.added.append(value)
    async def summary(messages):
        return {"important_events": [{"event_type": "goal", "title": "Launch"}], "open_loops": [{"title": "Check launch", "follow_up_at": "2026-01-02T10:00:00+00:00"}]}
    monkeypatch.setattr(tasks, "summarize_session", summary)
    assert await process_session(session, db)
    assert session.is_processed and db.commits == 1
    assert len(db.added) == 2


@pytest.mark.asyncio
async def test_process_session_normalizes_corrupt_messages_and_memory(monkeypatch):
    user = User(id=6, first_name="Test", memory=["corrupt"], tech_stack={})
    user.checkins_enabled = False
    session = Session(id=10, user_id=6, raw_messages=[["corrupt"], {"role": "user", "content": "Я живу в Москве"}], user=user)
    db = SimpleNamespace(added=[], commits=0)
    async def commit(): db.commits += 1
    db.commit = commit
    db.add = lambda value: db.added.append(value)
    async def summary(messages):
        assert messages == [{"role": "user", "content": "Я живу в Москве"}]
        return {"preferences": {"city": "Москва"}}
    monkeypatch.setattr(tasks, "summarize_session", summary)
    assert await process_session(session, db)
    assert isinstance(user.memory, dict)
    assert '"preferences"' in session.summary
