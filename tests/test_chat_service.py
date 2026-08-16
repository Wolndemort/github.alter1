import pytest
from types import SimpleNamespace

from data.models import Session, User
from services.chat_service import ChatService, _refresh_active_context, _stream_system_prompt, validate_message


def test_chat_message_is_trimmed():
    assert validate_message("  привет  ") == "привет"


def test_chat_message_cannot_be_empty():
    with pytest.raises(ValueError, match="empty"):
        validate_message("  ")


def test_chat_message_has_prompt_safety_limit(monkeypatch):
    from services import chat_service

    monkeypatch.setattr(chat_service.config, "AI_MAX_PROMPT_CHARS", 3)
    with pytest.raises(ValueError, match="too long"):
        validate_message("1234")


def test_short_stream_prompt_is_smaller_but_tool_prompt_keeps_full_policy():
    short = _stream_system_prompt("Привет", {}, use_tools=False)
    tool = _stream_system_prompt("Привет", {}, use_tools=True)
    assert len(short) < len(tool)
    assert "<user_memory>" in short
    assert "<user_memory>" in tool


def test_full_reply_memory_budget_keeps_core_categories_first():
    from utils.ap_logic import _bounded_memory
    value = {
        "identity": {"name": "Адам"},
        "family": {"family": "Седа и Магомед"},
        "skills_career": {"job": "дизайн"},
        "active_reminders": {"items": "x" * 5000},
    }
    bounded = _bounded_memory(value, 180)
    assert bounded["identity"]["name"] == "Адам"
    assert bounded["family"]["family"] == "Седа и Магомед"


@pytest.mark.asyncio
async def test_active_context_summary_refreshes_only_older_dialogue(monkeypatch):
    session = Session(raw_messages=[
        {"role": role, "content": f"{role}-{index}"}
        for index in range(8)
        for role in ("user", "assistant")
    ])
    captured = {}

    async def summarize(messages, previous_summary):
        captured["messages"] = messages
        captured["previous"] = previous_summary
        return "Текущая тема: проект; следующий шаг: продолжить."

    monkeypatch.setattr("services.chat_service.summarize_active_context", summarize)
    await _refresh_active_context(session)

    assert session.context_summary.startswith("Текущая тема")
    assert session.context_summary_messages == 16
    assert len(captured["messages"]) == 8


class Result:
    def __init__(self, value=None, values=None): self.value, self.values = value, values or []
    def scalar_one_or_none(self): return self.value
    def scalars(self): return self.values


class Db:
    def __init__(self, user, active=None, events=None):
        self.user, self.active, self.events = user, active, events or []
        self.added = []
        self.committed = False
    async def get(self, model, user_id): return self.user if model is User and user_id == self.user.id else None
    async def execute(self, statement):
        return Result(self.active if not self.added else self.active, self.events) if self.added == [] else Result(self.active, self.events)
    def add(self, value):
        if isinstance(value, Session): value.id = 12
        self.added.append(value)
    async def flush(self): pass
    async def commit(self): self.committed = True


@pytest.mark.asyncio
async def test_chat_service_creates_session_recalls_memory_and_persists(monkeypatch):
    user = User(id=5, first_name="Adam", memory={"goals": ["launch"]}, tech_stack={})
    db = Db(user, active=None, events=[SimpleNamespace(title="Milestone", event_type="goal", importance="high", description="ship")])
    recalled = []

    async def fake_recall(db, user_id, text):
        recalled.append((user_id, text)); return ["previous context"]
    async def fake_remember(db, user_id, text, source, categories=None):
        assert source == "user_message"
    async def fake_reply(messages, memory):
        assert memory["goals"] == ["launch"]
        assert memory["important_events"][0]["title"] == "Milestone"
        assert memory["related_previous_context"] == ["previous context"]
        return "assistant reply"
    monkeypatch.setattr("services.chat_service.recall", fake_recall)
    monkeypatch.setattr("services.chat_service.remember", fake_remember)
    monkeypatch.setattr("services.chat_service.generate_reply", fake_reply)
    monkeypatch.setattr("services.chat_service.config.MEMORY_AUTO_RECALL_MIN_CHARS", 1)

    result = await ChatService().reply(db, 5, "Вернись к предыдущему контексту")

    assert result.reply == "assistant reply"
    assert result.session_id == 12
    assert recalled and db.committed
    assert db.added[0].raw_messages[0]["role"] == "user"
    assert db.added[0].raw_messages[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_chat_service_rejects_missing_user():
    class EmptyDb:
        async def get(self, model, user_id): return None
    with pytest.raises(ValueError, match="user not found"):
        await ChatService().reply(EmptyDb(), 404, "hello")


@pytest.mark.asyncio
async def test_chat_service_completes_pending_reminder_without_hijacking_unrelated_text():
    user = User(id=21, first_name="Adam", memory={}, tech_stack={}, pending_reminder={"text": "проверить отчёт"})
    db = Db(user, active=None)
    result = await ChatService().reply(db, 21, "завтра в 10:00")
    assert result.reply.startswith("Записал. Напомню")
    assert user.pending_reminder == {}
    assert any(getattr(item, "text", "") == "проверить отчёт" for item in db.added)


@pytest.mark.asyncio
async def test_chat_service_routes_weather_through_shared_backend(monkeypatch):
    user = User(id=8, first_name="Weather", memory={}, tech_stack={})
    db = Db(user, active=None, events=[])
    async def weather(city):
        assert city
        return "weather result"
    monkeypatch.setattr("services.chat_service.get_weather", weather)
    monkeypatch.setattr("services.chat_service.is_weather_request", lambda text: True)
    async def remember(*args, **kwargs): pass
    monkeypatch.setattr("services.chat_service.remember", remember)
    result = await ChatService().reply(db, 8, "погода в Москве")
    assert result.reply == "weather result"


@pytest.mark.asyncio
async def test_chat_service_saves_vehicle_fact_immediately(monkeypatch):
    user = User(id=9, first_name="Adam", memory={}, tech_stack={})
    db = Db(user, active=None, events=[])
    async def remember(*args, **kwargs): pass
    async def reply(messages, memory):
        assert memory["preferences"]["vehicle"] == "BMW X5"
        return "Запомнил"
    monkeypatch.setattr("services.chat_service.remember", remember)
    monkeypatch.setattr("services.chat_service.generate_reply", reply)
    result = await ChatService().reply(db, 9, "У меня машина BMW X5")
    assert result.reply == "Запомнил"
    assert user.memory["preferences"]["vehicle"] == "BMW X5"


@pytest.mark.asyncio
async def test_chat_service_saves_explicit_memory_fact_for_mobile(monkeypatch):
    user = User(id=10, first_name="Adam", memory={}, tech_stack={})
    db = Db(user, active=None, events=[])
    async def remember(*args, **kwargs): pass
    async def reply(messages, memory): return "Запомнил"
    monkeypatch.setattr("services.chat_service.remember", remember)
    monkeypatch.setattr("services.chat_service.generate_reply", reply)
    await ChatService().reply(db, 10, "Запомни, что я люблю бегать по утрам")
    assert "я люблю бегать по утрам" in user.memory["preferences"]["explicit_facts"]


@pytest.mark.asyncio
async def test_private_mode_does_not_persist_session_memory_or_action_log(monkeypatch):
    user = User(id=11, first_name="Private", memory={}, tech_stack={"private_mode": True})
    db = Db(user, active=None, events=[])
    async def reply(messages, memory):
        assert messages[-1]["content"] == "секретный вопрос"
        return "ответ без сохранения"
    async def remember(*args, **kwargs):
        raise AssertionError("private mode must not save vector memory")
    monkeypatch.setattr("services.chat_service.generate_reply", reply)
    monkeypatch.setattr("services.chat_service.remember", remember)

    result = await ChatService().reply(db, 11, "секретный вопрос")

    assert result.reply == "ответ без сохранения"
    assert result.session_id == 0
    assert db.added == []
    assert user.memory == {}
    assert "_action_log" not in user.tech_stack
