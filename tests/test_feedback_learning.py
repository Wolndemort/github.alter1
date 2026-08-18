from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from services.feedback_learning import feedback_learning_context, feedback_poll_due, record_feedback


def test_feedback_is_recorded_as_bounded_learning_signal():
    user = SimpleNamespace(tech_stack={})
    entry = record_feedback(user, "negative", question="Что делать?", answer="Слишком длинный ответ", source="web")

    assert entry["source"] == "web"
    assert feedback_learning_context(user) == [{"rating": "negative", "question": "Что делать?", "answer": "Слишком длинный ответ"}]
    assert user.tech_stack["feedback_totals"] == {"positive": 0, "negative": 1}


def test_feedback_rejects_invalid_or_internal_content():
    with pytest.raises(ValueError):
        record_feedback(SimpleNamespace(tech_stack={}), "maybe", answer="answer")
    with pytest.raises(ValueError):
        record_feedback(SimpleNamespace(tech_stack={}), "positive", answer="")


def test_feedback_poll_is_due_every_72_hours():
    now = datetime.now(timezone.utc)
    user = SimpleNamespace(tech_stack={"last_feedback_poll_at": (now - timedelta(hours=71)).isoformat()})
    assert not feedback_poll_due(user, now)
    user.tech_stack["last_feedback_poll_at"] = (now - timedelta(hours=72)).isoformat()
    assert feedback_poll_due(user, now)
