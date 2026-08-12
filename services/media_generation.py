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
import logging

from config import config
from utils.url_safety import validate_public_url


class MediaGenerationError(ValueError):
    """A safe, user-facing generation error."""


def _provider_detail(response: httpx.Response) -> str:
    """Return short provider diagnostics without exposing credentials."""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("error") or payload.get("message")
        else:
            detail = payload
        return str(detail)[:240]
    except (ValueError, TypeError):
        return response.text[:240]


@dataclass(frozen=True)
class MediaArtifact:
    media_type: str
    data: bytes
    filename: str


def fal_capabilities() -> dict[str, Any]:
    """Return the configured Fal model contracts without exposing credentials."""
    return {
        "provider": config.MEDIA_PROVIDER,
        "models": {
            "image": {
                "id": config.FAL_IMAGE_MODEL,
                "mode": "image-to-image",
                "requires_source": True,
                "options": {
                    "aspect_ratio": ["21:9", "16:9", "4:3", "3:2", "1:1", "2:3", "3:4", "9:16", "9:21"],
                    "seed": "integer",
                    "guidance_scale": "number",
                    "sync_mode": "boolean",
                    "num_images": "integer",
                    "output_format": ["jpeg", "png", "webp"],
                    "safety_tolerance": ["1", "2", "3", "4", "5"],
                    "enhance_prompt": "boolean",
                    "image_prompt_strength": "number",
                },
            },
            "video": {
                "id": config.FAL_VIDEO_MODEL,
                "mode": "image-to-video",
                "requires_source": True,
                "options": {
                    "duration": ["5", "10"],
                    "negative_prompt": "string",
                    "cfg_scale": "number",
                    "generate_audio": "boolean",
                    "shot_type": ["customize", "intelligent"],
                    "aspect_ratio": ["16:9", "9:16", "1:1"],
                    "tail_image_url": "url",
                    "static_mask_url": "url",
                    "dynamic_masks": "array",
                    "keep_original_sound": "boolean",
                    "character_orientation": ["image", "video"],
                    "elements": "array",
                    "input_image_urls": "array",
                    "effect_scene": "string",
                    "face_id": "string",
                    "face_image": "url",
                    "start_time": "number",
                    "end_time": "number",
                    "audio_url": "url",
                    "camera_control": "object",
                    "advanced_camera_control": "object",
                    "voice_ids": "array",
                    "mask_url": "url",
                    "trajectories": "array",
                    "sound_start_time": "number",
                    "sound_end_time": "number",
                    "sound_insert_time": "number",
                    "sound_volume": "number",
                    "original_audio_volume": "number",
                },
            },
            "text_image": {"id": config.FAL_TEXT_IMAGE_MODEL, "mode": "text-to-image", "requires_source": False, "options": {"aspect_ratio": "enum", "seed": "integer", "sync_mode": "boolean", "num_images": "integer", "output_format": ["jpeg", "png", "webp"], "safety_tolerance": ["1", "2", "3", "4", "5"], "enhance_prompt": "boolean", "image_prompt_strength": "number"}},
            "text_video": {"id": config.FAL_TEXT_VIDEO_MODEL, "mode": "text-to-video", "requires_source": False, "options": {"duration": ["5", "10"], "aspect_ratio": ["16:9", "9:16", "1:1"], "negative_prompt": "string", "cfg_scale": "number", "generate_audio": "boolean", "shot_type": ["customize", "intelligent"], "multi_prompt": "array"}},
        },
    }


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
            attempts = max(1, int(config.MEDIA_GENERATION_RETRY_ATTEMPTS))
            response = None
            for attempt in range(attempts):
                response = await client.post(f"{base}/{model}", headers=headers, json=arguments)
                if response.status_code not in {408, 425, 429, 500, 502, 503, 504} or attempt == attempts - 1:
                    break
                logging.warning("media provider temporary failure model=%s status=%s retry=%s", model, response.status_code, attempt + 1)
                await asyncio.sleep(min(2 ** attempt, 4))
            assert response is not None
            logging.info("fal request submitted model=%s status=%s", model, response.status_code)
            if response.status_code in {402, 403}:
                logging.warning("fal request rejected model=%s status=%s detail=%s", model, response.status_code, _provider_detail(response))
                raise MediaGenerationError("fal.ai отклонил запрос: проверь баланс и API-ключ.")
            if response.status_code >= 400:
                logging.warning("fal request failed model=%s status=%s detail=%s", model, response.status_code, _provider_detail(response))
                raise MediaGenerationError("fal.ai временно недоступен или модель указана неверно.")
            payload = response.json()
            request_id = payload.get("request_id")
            logging.info("fal response model=%s request_id=%s keys=%s", model, request_id or "sync", sorted(payload.keys())[:20])
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
                logging.info("fal job status model=%s request_id=%s state=%s", model, request_id, state)
                if state == "COMPLETED":
                    result = await client.get(result_url, headers=headers)
                    if result.status_code >= 400:
                        raise MediaGenerationError("fal.ai не вернул результат задачи.")
                    payload = result.json()
                    logging.info("fal job result model=%s request_id=%s keys=%s", model, request_id, sorted(payload.keys())[:20])
                    return payload
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
        url = validate_public_url(url)
    except ValueError as exc:
        raise MediaGenerationError("provider returned an unsafe artifact URL") from exc
    try:
        async with httpx.AsyncClient(timeout=config.MEDIA_GENERATION_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            response.raise_for_status()
            max_bytes = config.MEDIA_VIDEO_MAX_OUTPUT_BYTES if filename.endswith(".mp4") else config.MEDIA_MAX_OUTPUT_BYTES
            if len(response.content) == 0 or len(response.content) > max_bytes:
                raise MediaGenerationError("Провайдер вернул файл недопустимого размера.")
            media_type = response.headers.get("content-type", "image/png").split(";", 1)[0]
            logging.info("media artifact downloaded filename=%s bytes=%s media_type=%s", filename, len(response.content), media_type)
            allowed = {"image/png", "image/jpeg", "image/webp", "video/mp4", "video/webm"}
            if media_type not in allowed:
                raise MediaGenerationError("Провайдер вернул неподдерживаемый формат файла.")
            return MediaArtifact(media_type, response.content, filename)
    except httpx.HTTPError as exc:
        raise MediaGenerationError("fal.ai вернул недоступный файл.") from exc


async def generate_image(prompt: str, source: tuple[str, bytes] | None = None, options: dict[str, Any] | None = None) -> MediaArtifact:
    """Generate or edit an image through an OpenAI-compatible endpoint."""
    if not prompt.strip():
        raise MediaGenerationError("Опиши, как изменить изображение.")
    if config.MEDIA_PROVIDER.casefold() == "fal":
        model = config.FAL_IMAGE_MODEL if source else config.FAL_TEXT_IMAGE_MODEL
        if not model:
            raise MediaGenerationError("Модель fal.ai для изображений не настроена.")
        arguments: dict[str, Any] = {"prompt": prompt}
        if source:
            mime, data = source
            arguments["image_url"] = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
        if options:
            arguments.update(options)
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


async def edit_image(source: tuple[str, bytes], prompt: str | None = None, options: dict[str, Any] | None = None) -> MediaArtifact:
    """Edit an existing image through the canonical image pipeline."""
    from utils.media_edit import DEFAULT_IMAGE_EDIT_PROMPT

    return await generate_image(prompt or DEFAULT_IMAGE_EDIT_PROMPT, source, options)


async def generate_video(prompt: str, source: tuple[str, bytes] | None = None, options: dict[str, Any] | None = None) -> MediaArtifact:
    """Reserve the same contract for async video providers.

    Video generation needs a provider-specific job/polling protocol; silently
    treating a text-only vision response as a video would be incorrect.
    """
    if config.MEDIA_PROVIDER.casefold() == "fal":
        model = config.FAL_VIDEO_MODEL if source else config.FAL_TEXT_VIDEO_MODEL
        if not model:
            raise MediaGenerationError("Модель fal.ai для видео не настроена.")
        arguments: dict[str, Any] = {"prompt": prompt}
        if source:
            mime, data = source
            arguments["image_url"] = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
        if options:
            arguments.update(options)
        payload = await _fal_result(model, arguments)
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
