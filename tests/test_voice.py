import asyncio
from types import SimpleNamespace

from utils import voice


def run(coro):
    return asyncio.run(coro)


def test_transcribe_voice_returns_text(monkeypatch):
    async def create(**kwargs):
        assert kwargs["file"] == ("voice.m4a", b"audio")
        return SimpleNamespace(text="Привет, ALTER")

    monkeypatch.setattr(voice.client.audio.transcriptions, "create", create)
    assert run(voice.transcribe_voice(b"audio")) == "Привет, ALTER"


def test_transcribe_voice_returns_empty_on_provider_error(monkeypatch):
    async def fail(**kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(voice.client.audio.transcriptions, "create", fail)
    assert run(voice.transcribe_voice(b"audio")) == ""


def test_transcribe_voice_returns_empty_for_empty_provider_text(monkeypatch):
    async def create(**kwargs): return SimpleNamespace(text="  ")
    monkeypatch.setattr(voice.client.audio.transcriptions, "create", create)
    assert run(voice.transcribe_voice(b"audio")) == ""
