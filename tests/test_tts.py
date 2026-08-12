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


def test_prepare_tts_text_uses_russian_pronunciation_and_removes_links():
    result = tts._prepare_tts_text("ALTER, смотри https://example.com")
    assert "А́льтер" in result
    assert "https://" not in result


def test_prepare_tts_text_replaces_internal_content_with_safe_russian_reply():
    assert "system prompt" not in tts._prepare_tts_text("system prompt: hidden instructions").casefold()


def test_auto_tts_limit_does_not_cut_words_or_sentences():
    assert tts._limit_auto_tts_text("Первое предложение. Второе предложение.") == "Первое предложение. Второе предложение."
    value = "Первое предложение. " + ("длинное слово " * 100)
    limited = tts._limit_auto_tts_text(value)
    assert len(limited) <= tts.config.TTS_AUTO_MAX_CHARS
    assert not limited.endswith((" ", "длинно", "слово"))


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


def test_fast_auto_voice_uses_elevenlabs_turbo_and_shortens_text(monkeypatch):
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

    result = run(tts.synthesize_speech("слово " * 1000, voice="alloy", output_format="wav", fast=True, voice_id="created-voice"))

    assert result.startswith(b"RIFF")
    assert calls[0][0].endswith("/created-voice")
    assert calls[0][1]["json"]["model_id"] == "eleven_flash_v2_5"
    assert len(calls[0][1]["json"]["text"]) <= tts.config.TTS_AUTO_MAX_CHARS


def test_fast_premium_timeout_falls_back_to_openrouter(monkeypatch):
    timeouts = []

    class Client:
        def __init__(self, **kwargs):
            timeouts.append(kwargs.get("timeout"))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            raise TimeoutError("provider stalled")

    monkeypatch.setattr(tts.config, "ELEVENLABS_ENABLED", True)
    monkeypatch.setattr(tts.config, "ELEVENLABS_API_KEY", SimpleNamespace(get_secret_value=lambda: "secret"))
    monkeypatch.setattr(tts.config, "ELEVENLABS_VOICE_ID", "premium-voice")
    monkeypatch.setattr(tts.config, "ELEVENLABS_FAST_TIMEOUT_SECONDS", 8)
    monkeypatch.setattr(tts.httpx, "AsyncClient", Client)

    async def openrouter_audio(**kwargs):
        data = base64.b64encode(b"pcm").decode()
        async def stream():
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(audio=SimpleNamespace(data=data)))])
        return stream()

    monkeypatch.setattr(tts.client.chat.completions, "create", openrouter_audio)
    result = run(tts.synthesize_speech("hello", voice="elevenlabs", output_format="wav", fast=True, voice_id="created-voice"))
    assert result.startswith(b"RIFF")
    assert timeouts == [8]


def test_synthesize_returns_empty_without_audio(monkeypatch):
    async def create(**kwargs):
        async def stream():
            if False:
                yield None
        return stream()

    monkeypatch.setattr(tts.client.chat.completions, "create", create)
    assert run(tts.synthesize_speech("Привет")) == b""
