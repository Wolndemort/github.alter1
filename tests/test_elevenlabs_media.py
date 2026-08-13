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
    assert (await elevenlabs_media.design_voice("calm low narrator for a podcast"))["text"] == "Привет"
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


@pytest.mark.asyncio
async def test_design_voice_persists_preview_as_a_real_voice(monkeypatch):
    class VoiceResponse(Response):
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class VoiceClient(Client):
        async def post(self, url, **kwargs):
            self.calls.append(("post", url, kwargs))
            if url.endswith("/design"):
                return VoiceResponse({"previews": [{"generated_voice_id": "preview-123"}]})
            return VoiceResponse({"voice_id": "voice-123"})

    Client.calls = []
    monkeypatch.setattr(elevenlabs_media.config, "ELEVENLABS_API_KEY", SimpleNamespace(get_secret_value=lambda: "secret"))
    monkeypatch.setattr(elevenlabs_media.httpx, "AsyncClient", VoiceClient)

    result = await elevenlabs_media.design_voice("calm low narrator for a podcast")

    assert result["voice_id"] == "voice-123"
    assert Client.calls[-1][1].endswith("/v1/text-to-voice")
    design_call = next(call for call in Client.calls if call[1].endswith("/design"))
    assert design_call[2]["json"]["auto_generate_text"] is True


@pytest.mark.asyncio
async def test_design_voice_wraps_provider_timeout(monkeypatch):
    class TimeoutClient(Client):
        async def post(self, url, **kwargs):
            raise TimeoutError("provider timed out")

    monkeypatch.setattr(elevenlabs_media.config, "ELEVENLABS_API_KEY", SimpleNamespace(get_secret_value=lambda: "secret"))
    monkeypatch.setattr(elevenlabs_media.httpx, "AsyncClient", TimeoutClient)

    with pytest.raises(elevenlabs_media.ElevenLabsError, match="temporarily unavailable"):
        await elevenlabs_media.design_voice("calm low narrator for a podcast")


@pytest.mark.asyncio
async def test_design_voice_resolves_id_when_persist_response_omits_it(monkeypatch):
    class VoiceResponse(Response):
        def __init__(self, payload): self.payload = payload
        def json(self): return self.payload

    class VoiceClient(Client):
        async def post(self, url, **kwargs):
            self.calls.append(("post", url, kwargs))
            if url.endswith("/design"):
                return VoiceResponse({"previews": [{"generated_voice_id": "preview-456"}]})
            return VoiceResponse({"name": "ALTER voice"})
        async def get(self, url, **kwargs):
            self.calls.append(("get", url, kwargs))
            return VoiceResponse({"voices": [{"name": "ALTER voice", "voice_id": "voice-456", "created_at_unix": 10}]})

    Client.calls = []
    monkeypatch.setattr(elevenlabs_media.config, "ELEVENLABS_API_KEY", SimpleNamespace(get_secret_value=lambda: "secret"))
    monkeypatch.setattr(elevenlabs_media.httpx, "AsyncClient", VoiceClient)
    result = await elevenlabs_media.design_voice("calm low narrator for a podcast")
    assert result["voice_id"] == "voice-456"


@pytest.mark.asyncio
async def test_design_voice_rejects_provider_minimum_description_locally():
    with pytest.raises(elevenlabs_media.ElevenLabsError, match="20"):
        await elevenlabs_media.design_voice("спокойный голос")


@pytest.mark.asyncio
async def test_lookup_wraps_non_json_provider_response(monkeypatch):
    class HtmlResponse(Response):
        status_code = 200

        def json(self):
            raise ValueError("html")

    class HtmlClient(Client):
        async def get(self, url, **kwargs):
            self.calls.append(("get", url, kwargs))
            return HtmlResponse()

    monkeypatch.setattr(elevenlabs_media.config, "ELEVENLABS_API_KEY", SimpleNamespace(get_secret_value=lambda: "secret"))
    monkeypatch.setattr(elevenlabs_media.httpx, "AsyncClient", HtmlClient)
    with pytest.raises(elevenlabs_media.ElevenLabsError, match="temporarily unavailable"):
        await elevenlabs_media.list_voices()
    with pytest.raises(elevenlabs_media.ElevenLabsError, match="temporarily unavailable"):
        await elevenlabs_media.list_models()


@pytest.mark.asyncio
async def test_models_401_uses_safe_local_catalog(monkeypatch):
    class UnauthorizedResponse(Response):
        status_code = 401

    class UnauthorizedClient(Client):
        async def get(self, url, **kwargs):
            self.calls.append(("get", url, kwargs))
            return UnauthorizedResponse()

    monkeypatch.setattr(elevenlabs_media.config, "ELEVENLABS_API_KEY", SimpleNamespace(get_secret_value=lambda: "secret"))
    monkeypatch.setattr(elevenlabs_media.httpx, "AsyncClient", UnauthorizedClient)
    models = await elevenlabs_media.list_models()
    assert any(item["model_id"] == "scribe_v1" for item in models)


@pytest.mark.asyncio
async def test_transcription_and_speech_to_speech_wrap_provider_transport_errors(monkeypatch):
    class BrokenClient(Client):
        async def post(self, url, **kwargs):
            raise elevenlabs_media.httpx.ConnectTimeout("provider timeout")

    monkeypatch.setattr(elevenlabs_media.config, "ELEVENLABS_API_KEY", SimpleNamespace(get_secret_value=lambda: "secret"))
    monkeypatch.setattr(elevenlabs_media.httpx, "AsyncClient", BrokenClient)

    with pytest.raises(elevenlabs_media.ElevenLabsError, match="temporarily unavailable"):
        await elevenlabs_media.speech_to_text(b"voice")
    with pytest.raises(elevenlabs_media.ElevenLabsError, match="temporarily unavailable"):
        await elevenlabs_media.speech_to_speech(b"voice", "voice-id")
