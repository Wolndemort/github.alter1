"""Provider-neutral image/video generation contract.

The chat/vision path analyses media. This module is deliberately separate:
generation returns a real artifact or an explicit configuration/provider
error, never a fake text success.
"""
from __future__ import annotations

import base64
import asyncio
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


def _fal_key() -> str:
    if not config.MEDIA_GENERATION_API_KEY:
        raise MediaGenerationError("Ключ fal.ai не настроен на сервере.")
    return config.MEDIA_GENERATION_API_KEY.get_secret_value()


async def _fal_result(model: str, arguments: dict[str, Any]) -> dict[str, Any]:
    headers = {"Authorization": f"Key {_fal_key()}", "Content-Type": "application/json"}
    base = config.FAL_BASE_URL.rstrip("/")
    timeout = httpx.Timeout(config.MEDIA_GENERATION_TIMEOUT_SECONDS)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{base}/{model}", headers=headers, json=arguments)
            if response.status_code in {402, 403}:
                raise MediaGenerationError("fal.ai отклонил запрос: проверь баланс и API-ключ.")
            if response.status_code >= 400:
                raise MediaGenerationError("fal.ai временно недоступен или модель указана неверно.")
            payload = response.json()
            request_id = payload.get("request_id")
            if not request_id:
                return payload
            status_url = payload.get("status_url") or f"{base}/{model}/requests/{request_id}/status"
            result_url = payload.get("response_url") or f"{base}/{model}/requests/{request_id}"
            deadline = asyncio.get_running_loop().time() + config.MEDIA_GENERATION_TIMEOUT_SECONDS
            while asyncio.get_running_loop().time() < deadline:
                status = await client.get(status_url, headers=headers)
                if status.status_code in {402, 403}:
                    raise MediaGenerationError("fal.ai отклонил запрос: проверь баланс и API-ключ.")
                if status.status_code >= 400:
                    raise MediaGenerationError("fal.ai не смог проверить статус задачи.")
                state = status.json().get("status")
                if state == "COMPLETED":
                    result = await client.get(result_url, headers=headers)
                    if result.status_code >= 400:
                        raise MediaGenerationError("fal.ai не вернул результат задачи.")
                    return result.json()
                if state in {"FAILED", "CANCELLED"}:
                    raise MediaGenerationError("fal.ai не смог обработать запрос.")
                await asyncio.sleep(1)
            raise MediaGenerationError("fal.ai обрабатывает запрос слишком долго.")
    except MediaGenerationError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise MediaGenerationError("Не удалось связаться с fal.ai.") from exc


async def _download_artifact(url: str, filename: str) -> MediaArtifact:
    try:
        async with httpx.AsyncClient(timeout=config.MEDIA_GENERATION_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            response.raise_for_status()
            media_type = response.headers.get("content-type", "image/png").split(";", 1)[0]
            return MediaArtifact(media_type, response.content, filename)
    except httpx.HTTPError as exc:
        raise MediaGenerationError("fal.ai вернул недоступный файл.") from exc


async def generate_image(prompt: str, source: tuple[str, bytes] | None = None) -> MediaArtifact:
    """Generate or edit an image through an OpenAI-compatible endpoint."""
    if not prompt.strip():
        raise MediaGenerationError("Опиши, как изменить изображение.")
    if config.MEDIA_PROVIDER.casefold() == "fal":
        model = config.FAL_IMAGE_MODEL
        if not model:
            raise MediaGenerationError("Модель fal.ai для изображений не настроена.")
        arguments: dict[str, Any] = {"prompt": prompt}
        if source:
            mime, data = source
            arguments["image_url"] = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
        payload = await _fal_result(model, arguments)
        item = (payload.get("images") or payload.get("data") or [{}])[0]
        if item.get("url"):
            return await _download_artifact(item["url"], "alter-generated.png")
        if item.get("b64_json"):
            return MediaArtifact("image/png", base64.b64decode(item["b64_json"]), "alter-generated.png")
        raise MediaGenerationError("fal.ai не вернул изображение.")
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


async def generate_video(prompt: str, source: tuple[str, bytes] | None = None) -> MediaArtifact:
    """Reserve the same contract for async video providers.

    Video generation needs a provider-specific job/polling protocol; silently
    treating a text-only vision response as a video would be incorrect.
    """
    if config.MEDIA_PROVIDER.casefold() == "fal":
        if not config.FAL_VIDEO_MODEL:
            raise MediaGenerationError("Модель fal.ai для видео не настроена.")
        arguments: dict[str, Any] = {"prompt": prompt}
        if source:
            mime, data = source
            arguments["video_url"] = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
        payload = await _fal_result(config.FAL_VIDEO_MODEL, arguments)
        candidates = payload.get("videos") or payload.get("data") or []
        if isinstance(payload.get("video"), dict):
            candidates = [payload["video"], *candidates]
        item = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        if item.get("url"):
            return await _download_artifact(item["url"], "alter-generated.mp4")
        if item.get("b64_json"):
            return MediaArtifact("video/mp4", base64.b64decode(item["b64_json"]), "alter-generated.mp4")
        raise MediaGenerationError("fal.ai не вернул готовое видео.")
    if not config.MEDIA_VIDEO_API_URL or not config.MEDIA_VIDEO_MODEL:
        raise MediaGenerationError("Генерация видео пока не подключена на сервере.")
    raise MediaGenerationError("Генератор видео требует отдельного job-процесса.")
