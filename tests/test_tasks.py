from utils.tasks import extract_important_events, extract_followups


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
