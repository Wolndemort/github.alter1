from types import SimpleNamespace

import pytest

from services import elevenlabs_media


class Response:
    status_code = 200
    content = b"mp3"

    def json(self):
        return {"text": "Привет"}


class Client:
    calls = []

    def __init__(self, **kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return Response()
    async def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return Response()


@pytest.mark.asyncio
async def test_enabled_elevenlabs_operations_use_expected_endpoints(monkeypatch):
    Client.calls = []
    monkeypatch.setattr(elevenlabs_media.config, "ELEVENLABS_API_KEY", SimpleNamespace(get_secret_value=lambda: "secret"))
    monkeypatch.setattr(elevenlabs_media.httpx, "AsyncClient", Client)
    assert (await elevenlabs_media.speech_to_text(b"voice"))["text"] == "Привет"
    assert await elevenlabs_media.speech_to_speech(b"voice", "voice-id") == b"mp3"
    assert (await elevenlabs_media.design_voice("calm narrator"))["text"] == "Привет"
    assert await elevenlabs_media.list_voices()
    assert await elevenlabs_media.list_models()
    urls = [call[1] for call in Client.calls]
    assert "https://api.elevenlabs.io/v1/speech-to-text" in urls
    assert "https://api.elevenlabs.io/v1/speech-to-speech/voice-id" in urls
    assert "https://api.elevenlabs.io/v1/text-to-voice/design" in urls
    assert "https://api.elevenlabs.io/v2/voices" in urls
    assert "https://api.elevenlabs.io/v1/models" in urls


@pytest.mark.asyncio
async def test_sound_effect_requests_a_usable_default_duration(monkeypatch):
    Client.calls = []
    monkeypatch.setattr(elevenlabs_media.config, "ELEVENLABS_API_KEY", SimpleNamespace(get_secret_value=lambda: "secret"))
    monkeypatch.setattr(elevenlabs_media.httpx, "AsyncClient", Client)

    assert await elevenlabs_media.sound_effect("дождь") == b"mp3"
    call = Client.calls[0]
    assert call[1].endswith("/v1/sound-generation")
    assert call[2]["json"]["duration_seconds"] == 8
