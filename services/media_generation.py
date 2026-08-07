"""Provider-neutral image/video generation contract.

The chat/vision path analyses media. This module is deliberately separate:
generation returns a real artifact or an explicit configuration/provider
error, never a fake text success.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

import httpx

from config import config


class MediaGenerationError(ValueError):
    """A safe, user-facing generation error."""


@dataclass(frozen=True)
class MediaArtifact:
    media_type: str
    data: bytes
    filename: str


def _api_key() -> str:
    if not config.MEDIA_GENERATION_API_KEY:
        raise MediaGenerationError("Генерация медиа пока не настроена на сервере.")
    return config.MEDIA_GENERATION_API_KEY.get_secret_value()


def _url(path: str) -> str:
    if not config.MEDIA_GENERATION_API_URL:
        raise MediaGenerationError("Генерация медиа пока не настроена на сервере.")
    return config.MEDIA_GENERATION_API_URL.rstrip("/") + path


def _decode_image(payload: dict[str, Any]) -> MediaArtifact:
    item = (payload.get("data") or [{}])[0]
    encoded = item.get("b64_json")
    if encoded:
        return MediaArtifact("image/png", base64.b64decode(encoded), "alter-generated.png")
    url = item.get("url")
    if not url:
        raise MediaGenerationError("Провайдер не вернул изображение.")
    raise MediaGenerationError("Провайдер вернул временную ссылку вместо файла.")


async def generate_image(prompt: str, source: tuple[str, bytes] | None = None) -> MediaArtifact:
    """Generate or edit an image through an OpenAI-compatible endpoint."""
    if not prompt.strip():
        raise MediaGenerationError("Опиши, как изменить изображение.")
    model = config.MEDIA_IMAGE_MODEL
    if not model:
        raise MediaGenerationError("Модель генерации изображений не настроена на сервере.")
    headers = {"Authorization": f"Bearer {_api_key()}"}
    timeout = httpx.Timeout(config.MEDIA_GENERATION_TIMEOUT_SECONDS)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if source:
                mime, data = source
                response = await client.post(
                    _url("/images/edits"),
                    headers=headers,
                    data={"model": model, "prompt": prompt, "response_format": "b64_json"},
                    files={"image": ("input", data, mime)},
                )
            else:
                response = await client.post(
                    _url("/images/generations"),
                    headers=headers,
                    json={"model": model, "prompt": prompt, "response_format": "b64_json"},
                )
    except httpx.HTTPError as exc:
        raise MediaGenerationError("Сервис генерации изображений временно недоступен.") from exc
    if response.status_code >= 400:
        raise MediaGenerationError("Сервис генерации изображений временно недоступен.")
    try:
        return _decode_image(response.json())
    except (ValueError, KeyError, IndexError, base64.binascii.Error) as exc:
        raise MediaGenerationError("Не удалось получить изображение от сервиса.") from exc


async def generate_video(prompt: str, source: tuple[str, bytes] | None = None) -> None:
    """Reserve the same contract for async video providers.

    Video generation needs a provider-specific job/polling protocol; silently
    treating a text-only vision response as a video would be incorrect.
    """
    if not config.MEDIA_VIDEO_API_URL or not config.MEDIA_VIDEO_MODEL:
        raise MediaGenerationError("Генерация видео пока не подключена на сервере.")
    raise MediaGenerationError("Генератор видео требует отдельного job-процесса.")
