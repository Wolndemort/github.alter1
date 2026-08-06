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


def test_audio_helpers_handle_empty_and_dict_fragments():
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(audio={"data": None}))])
    assert tts._get_audio_data(response) == b""
    async def stream():
        yield SimpleNamespace(choices=[])
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(audio={"data": base64.b64encode(b"a").decode()}))])
        yield SimpleNamespace(choices=[SimpleNamespace(delta=None)])
    assert run(tts._get_stream_audio_data(stream())) == b"a"


def test_wav_conversion_returns_empty_when_ffmpeg_missing(monkeypatch):
    async def missing(*args, **kwargs): raise FileNotFoundError("ffmpeg")
    monkeypatch.setattr(tts.asyncio, "create_subprocess_exec", missing)
    assert run(tts._wav_to_ogg(b"RIFF")) == b""


def test_synthesize_returns_empty_when_provider_fails(monkeypatch):
    async def fail(**kwargs): raise RuntimeError("provider unavailable")
    monkeypatch.setattr(tts.client.chat.completions, "create", fail)
    assert run(tts.synthesize_speech("hello")) == b""


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
