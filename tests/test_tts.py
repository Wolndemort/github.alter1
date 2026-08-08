import asyncio
import base64
import pytest
from types import SimpleNamespace

from utils import tts


@pytest.fixture(autouse=True)
def disable_elevenlabs_for_unit_tests(monkeypatch):
    monkeypatch.setattr(tts.config, "ELEVENLABS_ENABLED", False)


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


def test_elevenlabs_is_used_only_for_explicit_premium_voice(monkeypatch):
    calls = []

    class Response:
        content = b"\x00\x00" * 32

        def raise_for_status(self):
            pass

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    monkeypatch.setattr(tts.config, "ELEVENLABS_ENABLED", True)
    monkeypatch.setattr(tts.config, "ELEVENLABS_API_KEY", SimpleNamespace(get_secret_value=lambda: "secret"))
    monkeypatch.setattr(tts.config, "ELEVENLABS_VOICE_ID", "premium-voice")
    monkeypatch.setattr(tts.httpx, "AsyncClient", Client)

    async def openrouter_audio(**kwargs):
        async def stream():
            if False:
                yield None
        return stream()

    monkeypatch.setattr(tts.client.chat.completions, "create", openrouter_audio)

    assert run(tts.synthesize_speech("hello", voice="alloy", output_format="wav")) == b""
    assert not calls
    result = run(tts.synthesize_speech("hello", voice="elevenlabs", output_format="wav"))
    assert result.startswith(b"RIFF")
    assert calls[0][0].endswith("/premium-voice")


def test_synthesize_returns_empty_without_audio(monkeypatch):
    async def create(**kwargs):
        async def stream():
            if False:
                yield None
        return stream()

    monkeypatch.setattr(tts.client.chat.completions, "create", create)
    assert run(tts.synthesize_speech("Привет")) == b""
