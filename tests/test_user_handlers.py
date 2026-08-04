from data.models import Session
from handlers.user_handlers import append_session_message, recent_context


def test_append_session_message_preserves_existing_transcript():
    session = Session(raw_messages=[{"role": "user", "content": "Привет"}])
    append_session_message(session, "assistant", "Привет! Чем помочь?")
    assert [item["role"] for item in session.raw_messages] == ["user", "assistant"]
    assert session.raw_messages[-1]["content"] == "Привет! Чем помочь?"
    assert session.raw_messages[-1]["timestamp"]


def test_append_session_message_handles_empty_transcript():
    session = Session(raw_messages=None)
    append_session_message(session, "user", "Сохрани это")
    assert session.raw_messages[0]["content"] == "Сохрани это"


def test_recent_context_limits_history_to_latest_messages():
    messages = [{"content": str(i)} for i in range(100)]
    assert [item["content"] for item in recent_context(messages)] == [str(i) for i in range(60, 100)]
