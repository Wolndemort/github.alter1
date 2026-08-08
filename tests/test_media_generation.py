from types import SimpleNamespace

import pytest

from services import media_generation


def test_generation_requires_explicit_provider(monkeypatch):
    monkeypatch.setattr(media_generation.config, "MEDIA_GENERATION_API_URL", None)
    with pytest.raises(media_generation.MediaGenerationError, match="не настроена"):
        media_generation._url("/images/generations")


@pytest.mark.asyncio
async def test_configured_fal_text_models_accept_prompts_without_source(monkeypatch):
    monkeypatch.setattr(media_generation.config, "MEDIA_PROVIDER", "fal")
    monkeypatch.setattr(media_generation.config, "FAL_IMAGE_MODEL", "fal-ai/test-image")
    monkeypatch.setattr(media_generation.config, "FAL_VIDEO_MODEL", "fal-ai/test-video")
    monkeypatch.setattr(media_generation.config, "FAL_TEXT_IMAGE_MODEL", "fal-ai/test-text-image")
    monkeypatch.setattr(media_generation.config, "FAL_TEXT_VIDEO_MODEL", "fal-ai/test-text-video")

    async def fake_result(model, arguments):
        assert model in {"fal-ai/test-text-image", "fal-ai/test-text-video"}
        assert "prompt" in arguments and "image_url" not in arguments
        return {"images": [{"b64_json": "aGVsbG8="}]} if "image" in model else {"videos": [{"b64_json": "aGVsbG8="}]}

    monkeypatch.setattr(media_generation, "_fal_result", fake_result)
    assert (await media_generation.generate_image("create")).data == b"hello"
    assert (await media_generation.generate_video("animate")).data == b"hello"


@pytest.mark.asyncio
async def test_image_generation_decodes_provider_artifact(monkeypatch):
    monkeypatch.setattr(media_generation.config, "MEDIA_PROVIDER", "openai_compatible")
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
    monkeypatch.setattr(media_generation.config, "MEDIA_PROVIDER", "openai_compatible")
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
        await media_generation.generate_image("cinematic", ("image/jpeg", b"input"))


@pytest.mark.asyncio
async def test_fal_image_returns_downloaded_artifact(monkeypatch):
    monkeypatch.setattr(media_generation.config, "MEDIA_PROVIDER", "fal")
    monkeypatch.setattr(media_generation.config, "FAL_IMAGE_MODEL", "fal-ai/test-image")
    monkeypatch.setattr(media_generation.config, "MEDIA_GENERATION_API_KEY", SimpleNamespace(get_secret_value=lambda: "key"))

    class Response:
        status_code = 200
        headers = {"content-type": "image/png"}
        content = b"png"
        def json(self): return {"images": [{"url": "https://cdn.example/image.png"}]}
        def raise_for_status(self): pass

    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return Response()
        async def get(self, *args, **kwargs): return Response()

    monkeypatch.setattr(media_generation.httpx, "AsyncClient", Client)
    result = await media_generation.generate_image("cinematic", ("image/jpeg", b"input"), {"aspect_ratio": "16:9"})
    assert result.data == b"png"
