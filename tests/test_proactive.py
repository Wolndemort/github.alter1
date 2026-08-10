from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from utils.tasks import active_open_loops, proactive_allowed


def test_proactive_ignores_completed_loops():
    assert active_open_loops({"open_loops": [{"title": "done", "status": "done"}, {"title": "active"}]}) == [{"title": "active"}]


def test_proactive_does_not_interrupt_recent_chat_or_interval():
    now = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)
    user = SimpleNamespace(tech_stack={}, last_checkin_at=None)
    recent = SimpleNamespace(updated_at=now - timedelta(minutes=5))
    assert proactive_allowed(user, now, recent, 24) is False
    user.last_checkin_at = now - timedelta(hours=1)
    assert proactive_allowed(user, now, None, 24) is False


def test_proactive_can_be_disabled_explicitly():
    now = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)
    user = SimpleNamespace(tech_stack={"proactive_enabled": False}, last_checkin_at=None)
    assert proactive_allowed(user, now, None, 24) is False
