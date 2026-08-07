from types import SimpleNamespace

import pytest

from services import media_generation


def test_generation_requires_explicit_provider(monkeypatch):
    monkeypatch.setattr(media_generation.config, "MEDIA_GENERATION_API_URL", None)
    with pytest.raises(media_generation.MediaGenerationError, match="не настроена"):
        media_generation._url("/images/generations")


@pytest.mark.asyncio
async def test_image_generation_decodes_provider_artifact(monkeypatch):
    monkeypatch.setattr(media_generation.config, "MEDIA_GENERATION_API_URL", "https://media.example/v1")
    monkeypatch.setattr(media_generation.config, "MEDIA_GENERATION_API_KEY", SimpleNamespace(get_secret_value=lambda: "secret"))
    monkeypatch.setattr(media_generation.config, "MEDIA_IMAGE_MODEL", "image-model")

    class Response:
        status_code = 200
        def json(self): return {"data": [{"b64_json": "aGVsbG8="}]}

    class Client:
        def __init__(self, **kwargs): self.kwargs = kwargs
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            assert url.endswith("/images/edits")
            assert kwargs["data"]["model"] == "image-model"
            return Response()

    monkeypatch.setattr(media_generation.httpx, "AsyncClient", Client)
    result = await media_generation.generate_image("make it cinematic", ("image/jpeg", b"input"))
    assert result.data == b"hello"
    assert result.media_type == "image/png"


@pytest.mark.asyncio
async def test_video_generation_is_explicitly_not_fake(monkeypatch):
    monkeypatch.setattr(media_generation.config, "MEDIA_VIDEO_API_URL", None)
    with pytest.raises(media_generation.MediaGenerationError, match="видео"):
        await media_generation.generate_video("cinematic")


@pytest.mark.asyncio
async def test_fal_zero_balance_is_safe_error(monkeypatch):
    monkeypatch.setattr(media_generation.config, "MEDIA_PROVIDER", "fal")
    monkeypatch.setattr(media_generation.config, "FAL_IMAGE_MODEL", "fal-ai/test-image")
    monkeypatch.setattr(media_generation.config, "MEDIA_GENERATION_API_KEY", SimpleNamespace(get_secret_value=lambda: "key"))

    class Response:
        status_code = 402
        def json(self): return {}

    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return Response()

    monkeypatch.setattr(media_generation.httpx, "AsyncClient", Client)
    with pytest.raises(media_generation.MediaGenerationError, match="баланс"):
        await media_generation.generate_image("cinematic")
