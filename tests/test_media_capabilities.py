from types import SimpleNamespace

from services import media_generation


def test_fal_capabilities_expose_models_and_options_without_secrets(monkeypatch):
    monkeypatch.setattr(media_generation.config, "MEDIA_PROVIDER", "fal")
    monkeypatch.setattr(media_generation.config, "FAL_IMAGE_MODEL", "fal-ai/image")
    monkeypatch.setattr(media_generation.config, "FAL_VIDEO_MODEL", "fal-ai/video")
    monkeypatch.setattr(media_generation.config, "MEDIA_GENERATION_API_KEY", SimpleNamespace(get_secret_value=lambda: "secret"))
    result = media_generation.fal_capabilities()
    assert result["models"]["image"]["id"] == "fal-ai/image"
    assert "aspect_ratio" in result["models"]["image"]["options"]
    assert "camera_control" in result["models"]["video"]["options"]
    assert result["models"]["text_image"]["mode"] == "text-to-image"
    assert result["models"]["text_video"]["mode"] == "text-to-video"
    assert "secret" not in str(result)
