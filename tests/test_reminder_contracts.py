import importlib.util
from pathlib import Path

from data.models import Reminder, User
from utils import checkins
from utils.checkins import QUESTIONS, contextual_checkin, random_checkin
from utils.reminders import looks_like_time_answer, parse_reminder, parse_time_answer


def load_migration(name):
    path = Path(__file__).parents[1] / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reminder_model_has_delivery_and_follow_up_contract():
    columns = Reminder.__table__.columns
    names = set(columns.keys())
    assert {"user_id", "text", "remind_at", "is_sent", "kind"} <= names
    assert {"follow_up_at", "follow_up_sent"} <= names


def test_user_has_opt_in_checkin_contract():
    columns = User.__table__.columns
    assert {"checkins_enabled", "last_checkin_at"} <= set(columns.keys())


def test_checkin_question_is_safe_and_bounded():
    assert QUESTIONS
    assert all("диагноз" not in question.lower() for question in QUESTIONS)
    assert random_checkin() in QUESTIONS


def test_contextual_checkin_uses_name_and_explicit_context():
    result = contextual_checkin("Адам", "проект ALTER")
    assert result.startswith("Адам, ")
    assert "проект ALTER" in result


def test_model_checkin_uses_context(monkeypatch):
    async def fake_chat(messages, max_tokens=None):
        assert "проект ALTER" in messages[1]["content"]
        assert "не используй шаблонные" in messages[0]["content"].casefold()
        class Response:
            choices = [type("Choice", (), {"message": type("Message", (), {"content": "Удалось сегодня продвинуться с проектом ALTER?"})()})()]
        return Response()

    monkeypatch.setattr(checkins, "chat_with_fallback", fake_chat)
    result = __import__("asyncio").run(checkins.generate_contextual_checkin("Адам", "проект ALTER"))
    assert result == "Удалось сегодня продвинуться с проектом ALTER?"


def test_reminder_parser_supports_day_and_relative_time():
    assert parse_reminder("завтра в 10:30 сходить к барберу")[1] == "сходить к барберу"
    assert parse_reminder("через 2 часа позвонить") is not None


def test_time_answer_rejects_invalid_time():
    assert parse_time_answer("в 25:90") is None


def test_time_answer_supports_natural_language_and_does_not_hijack_chat():
    assert parse_time_answer("в девять") is not None
    tomorrow = parse_time_answer("завтра в 10")
    assert tomorrow is not None
    assert tomorrow.hour == 10
    assert looks_like_time_answer("через 2 часа")
    assert not looks_like_time_answer("да, кстати расскажи про проект")


def test_migrations_form_current_linear_chain():
    expected = [
        ("0003_event_metadata.py", "0002_important_events"),
        ("0004_reminders.py", "0003_event_metadata"),
        ("0005_pending_reminders.py", "0004_reminders"),
        ("0006_reminder_follow_up.py", "0005_pending_reminders"),
        ("0007_checkins.py", "0006_reminder_follow_up"),
        ("0008_gentle_checkins.py", "0007_checkins"),
    ]
    for filename, parent in expected:
        migration = load_migration(filename)
        assert migration.down_revision == parent
