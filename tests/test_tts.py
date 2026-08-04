import asyncio
import base64
from types import SimpleNamespace

from utils import tts


def run(coro):
    return asyncio.run(coro)


def test_audio_data_is_decoded():
    raw = b"RIFF wav"
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        audio=SimpleNamespace(data=base64.b64encode(raw).decode())
    ))])
    assert tts._get_audio_data(response) == raw


def test_synthesize_uses_openrouter_audio_chat(monkeypatch):
    calls = {}

    async def create(**kwargs):
        calls.update(kwargs)
        data = base64.b64encode(b"wav").decode()
        async def stream():
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                audio=SimpleNamespace(data=data)
            ))])
        return stream()

    async def convert(data):
        assert data.startswith(b"RIFF")
        return b"ogg-opus"

    monkeypatch.setattr(tts.client.chat.completions, "create", create)
    monkeypatch.setattr(tts, "_wav_to_ogg", convert)
    assert run(tts.synthesize_speech("Привет")) == b"ogg-opus"
    assert calls["modalities"] == ["text", "audio"]
    assert calls["audio"]["format"] == "pcm16"
    assert calls["stream"] is True
    assert calls["max_tokens"] == 1024
    assert len(calls["messages"][0]["content"]) <= 1200


def test_synthesize_returns_empty_without_audio(monkeypatch):
    async def create(**kwargs):
        async def stream():
            if False:
                yield None
        return stream()

    monkeypatch.setattr(tts.client.chat.completions, "create", create)
    assert run(tts.synthesize_speech("Привет")) == b""
