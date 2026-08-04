from datetime import datetime

from utils.reminders import parse_reminder


def test_parse_reminder_rejects_ambiguous_plan():
    assert parse_reminder("завтра иду к барберу") is None


def test_parse_reminder_parses_explicit_time():
    result = parse_reminder("завтра в 10:30 сходить к барберу")
    assert result is not None
    remind_at, text = result
    assert remind_at.hour == 10
    assert remind_at.minute == 30
    assert text == "сходить к барберу"
