import asyncio
from types import SimpleNamespace

from utils import media_logic
from utils.media import video_audio, video_preview
from utils.prompts import MEDIA_SYSTEM_PROMPT


def run(coro):
    return asyncio.run(coro)


def test_media_reply_sends_image_as_data_url(monkeypatch):
    captured = {}

    async def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Это скриншот ошибки."))])

    monkeypatch.setattr(media_logic.client.chat.completions, "create", create)
    result = run(media_logic.generate_media_reply("Что здесь?", [("image/jpeg", b"fake-image")]))
    content = captured["messages"][1]["content"]
    assert result == "Это скриншот ошибки."
    assert content[0]["text"] == "Что здесь?"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_media_reply_preserves_conversation_context(monkeypatch):
    captured = {}

    async def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Вижу продолжение темы."))])

    monkeypatch.setattr(media_logic.client.chat.completions, "create", create)
    run(media_logic.generate_media_reply(
        "Посмотри этот скрин",
        [("image/jpeg", b"fake-image")],
        conversation_context=[{"role": "user", "content": "Мы обсуждали духи René de Nuit"}],
        memory={"preferences": {"fragrance": "нишевые ароматы"}},
    ))
    messages = captured["messages"]
    assert messages[1] == {"role": "user", "content": "Мы обсуждали духи René de Nuit"}
    assert "нишевые ароматы" in messages[0]["content"]


def test_media_reply_returns_safe_error(monkeypatch):
    async def fail(**kwargs):
        raise RuntimeError("vision unavailable")

    monkeypatch.setattr(media_logic.client.chat.completions, "create", fail)
    result = run(media_logic.generate_media_reply("Разбери", [("image/jpeg", b"bad")]))
    assert "Не удалось проанализировать" in result


def test_video_preview_handles_invalid_video():
    assert run(video_preview(b"not a video")) == []


def test_video_audio_handles_invalid_video():
    assert run(video_audio(b"not a video")) == b""


def test_media_prompt_is_clean_utf8_and_sets_capabilities():
    assert "мультимодальный ALTER" in MEDIA_SYSTEM_PROMPT
    assert "Не выдумывай" in MEDIA_SYSTEM_PROMPT
