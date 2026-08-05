import asyncio
from types import SimpleNamespace

from data.models import Session, User
from handlers import user_handlers
from utils import ap_logic
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


def test_recent_context_keeps_latest_messages_within_budget():
    messages = [{"role": "user", "content": f"message-{index}-" + ("x" * 20)} for index in range(10)]
    result = recent_context(messages, max_chars=55)
    assert result[-1] == messages[-1]
    assert len(result) < len(messages)
    assert sum(len(item["content"]) for item in result) <= 55


def test_recent_context_limits_history_to_latest_messages():
    messages = [{"content": str(i)} for i in range(100)]
    assert [item["content"] for item in recent_context(messages)] == [str(i) for i in range(60, 100)]


def test_plain_message_offline_handler_flow(monkeypatch):
    user = User(id=42, first_name="Test", memory={}, tech_stack={})
    user.pending_reminder = {}
    session = Session(user_id=42, raw_messages=[])
    answers = []
    actions = []

    class Result:
        def scalar_one_or_none(self):
            return None

        def scalars(self):
            return iter(())

    class DB:
        async def get(self, model, key):
            return user

        async def execute(self, statement):
            return Result()

        def add(self, item):
            if isinstance(item, Session):
                self.session = item

        async def flush(self):
            pass

        async def commit(self):
            pass

        async def refresh(self, item):
            pass

    class Bot:
        async def send_chat_action(self, chat_id, action):
            actions.append((chat_id, action))

    class Message:
        text = "Привет, расскажи коротко о себе"
        from_user = SimpleNamespace(id=42, username="test", first_name="Test")
        chat = SimpleNamespace(id=100)
        bot = Bot()

        async def answer(self, text):
            answers.append(text)

    async def fake_reply(messages, memory, search_results):
        assert messages[-1]["content"] == Message.text
        assert memory == {}
        return "Ответ из offline smoke-теста"

    async def no_recall(*args):
        return []

    async def no_remember(*args, **kwargs):
        pass

    async def fake_answer(message, reply, current_user, force_voice=False):
        await message.answer(reply)

    monkeypatch.setattr(user_handlers, "generate_reply", fake_reply)
    monkeypatch.setattr(user_handlers, "recall", no_recall)
    monkeypatch.setattr(user_handlers, "remember", no_remember)
    monkeypatch.setattr(user_handlers, "answer_reply", fake_answer)

    asyncio.run(user_handlers.handle_any_message(Message(), DB()))

    assert answers == ["Ответ из offline smoke-теста"]
    assert actions == [(100, "typing")]


def test_handler_returns_safe_reply_when_ai_is_unavailable(monkeypatch):
    user = User(id=43, first_name="Test", memory={}, tech_stack={})
    user.pending_reminder = {}
    answers = []

    class Result:
        def scalar_one_or_none(self):
            return None

        def scalars(self):
            return iter(())

    class DB:
        async def get(self, model, key):
            return user

        async def execute(self, statement):
            return Result()

        def add(self, item):
            pass

        async def flush(self):
            pass

        async def commit(self):
            pass

        async def refresh(self, item):
            pass

    class Bot:
        async def send_chat_action(self, chat_id, action):
            pass

    class Message:
        text = "Помоги мне, пожалуйста"
        from_user = SimpleNamespace(id=43, username="test", first_name="Test")
        chat = SimpleNamespace(id=101)
        bot = Bot()

        async def answer(self, text):
            answers.append(text)

    async def ai_failure(**kwargs):
        raise RuntimeError("provider unavailable")

    async def no_recall(*args):
        return []

    async def no_remember(*args, **kwargs):
        pass

    async def fake_answer(message, reply, current_user, force_voice=False):
        await message.answer(reply)

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", ai_failure)
    monkeypatch.setattr(user_handlers, "recall", no_recall)
    monkeypatch.setattr(user_handlers, "remember", no_remember)
    monkeypatch.setattr(user_handlers, "answer_reply", fake_answer)

    asyncio.run(user_handlers.handle_any_message(Message(), DB()))

    assert len(answers) == 1
    assert "не удалось получить ответ" in answers[0].lower()
