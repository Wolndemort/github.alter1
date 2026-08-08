import asyncio
from types import SimpleNamespace

from handlers import user_handlers


def run(coro):
    return asyncio.run(coro)


class FakeMessage:
    def __init__(self):
        self.text_replies = []
        self.voice_replies = []

    async def answer(self, text):
        self.text_replies.append(text)

    async def answer_voice(self, audio):
        self.voice_replies.append(audio)


def test_answer_reply_sends_text_and_enabled_voice(monkeypatch):
    message = FakeMessage()
    user = SimpleNamespace(tech_stack={"voice_replies": True})

    async def synthesize(text, **kwargs):
        return b"voice"

    monkeypatch.setattr(user_handlers, "synthesize_speech", synthesize)
    run(user_handlers.answer_reply(message, "Ответ", user))

    assert message.text_replies == ["Ответ"]
    assert len(message.voice_replies) == 1
    assert message.voice_replies[0].filename == "alter.ogg"


def test_answer_reply_keeps_text_when_tts_fails(monkeypatch):
    message = FakeMessage()
    user = SimpleNamespace(tech_stack={"voice_replies": True})

    async def synthesize(text, **kwargs):
        return b""

    monkeypatch.setattr(user_handlers, "synthesize_speech", synthesize)
    run(user_handlers.answer_reply(message, "Ответ", user))

    assert message.text_replies == ["Ответ"]
    assert message.voice_replies == []


def test_answer_reply_force_voice_ignores_user_setting(monkeypatch):
    message = FakeMessage()
    user = SimpleNamespace(tech_stack={"voice_replies": False})

    async def synthesize(text, **kwargs):
        return b"voice"

    monkeypatch.setattr(user_handlers, "synthesize_speech", synthesize)
    run(user_handlers.answer_reply(message, "Ответ", user, force_voice=True))

    assert len(message.voice_replies) == 1


def test_answer_reply_does_not_send_voice_when_disabled(monkeypatch):
    message = FakeMessage()
    user = SimpleNamespace(tech_stack={"voice_replies": False})

    async def synthesize(text, **kwargs):
        return b"voice"

    monkeypatch.setattr(user_handlers, "synthesize_speech", synthesize)
    run(user_handlers.answer_reply(message, "Ответ", user))

    assert message.text_replies == ["Ответ"]
    assert message.voice_replies == []
