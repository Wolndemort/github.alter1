from datetime import datetime

from utils.reminders import extract_reminder_text, is_reminder_request, parse_reminder


def test_parse_reminder_rejects_ambiguous_plan():
    assert parse_reminder("завтра иду к барберу") is None


def test_parse_reminder_parses_explicit_time():
    result = parse_reminder("завтра в 10:30 сходить к барберу")
    assert result is not None
    remind_at, text = result
    assert remind_at.hour == 10
    assert remind_at.minute == 30
    assert text == "сходить к барберу"


def test_parser_separates_trigger_fillers_time_and_task():
    result = parse_reminder("Напомни мне в 10 утра позвонить маме")
    assert result is not None
    remind_at, task = result
    assert remind_at.hour == 10
    assert task == "позвонить маме"


def test_parser_supports_time_after_task_and_day_parts():
    result = parse_reminder("Поставь напоминание позвонить маме завтра в 18:30")
    assert result is not None
    assert result[0].hour == 18 and result[0].minute == 30
    assert result[1] == "позвонить маме"


def test_parser_supports_relative_days_weekdays_and_month_dates():
    assert parse_reminder("Напомни через 2 дня проверить документы")[1] == "проверить документы"
    assert parse_reminder("Напомни в понедельник в 09:15 позвонить врачу")[1] == "позвонить врачу"
    assert parse_reminder("Напомни 30 декабря в 12:00 купить подарок")[1] == "купить подарок"


def test_missing_time_keeps_only_task_for_pending_reminder():
    assert is_reminder_request("напомни мне")
    assert extract_reminder_text("напомни мне, пожалуйста, про оплату интернета") == "оплату интернета"
    assert extract_reminder_text("напомни мне") == ""
