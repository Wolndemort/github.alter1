import asyncio

from utils import voice


def run(coro):
    return asyncio.run(coro)


def test_transcribe_voice_returns_text(monkeypatch):
    async def transcribe(*args, **kwargs):
        assert args == (b"audio", "voice.m4a")
        return {"text": "Привет, ALTER"}

    monkeypatch.setattr(voice, "speech_to_text", transcribe)
    assert run(voice.transcribe_voice(b"audio")) == "Привет, ALTER"


def test_transcribe_voice_returns_empty_on_provider_error(monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(voice, "speech_to_text", fail)
    assert run(voice.transcribe_voice(b"audio")) == ""


def test_transcribe_voice_returns_empty_for_empty_provider_text(monkeypatch):
    async def transcribe(*args, **kwargs): return {"text": "  "}
    monkeypatch.setattr(voice, "speech_to_text", transcribe)
    assert run(voice.transcribe_voice(b"audio")) == ""
