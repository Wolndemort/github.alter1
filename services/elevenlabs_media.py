"""Small ElevenLabs media adapter used by HTTP and Telegram clients."""
from __future__ import annotations

import httpx
import logging

from config import config
from utils.http_pool import client as pooled_client


class ElevenLabsError(RuntimeError):
    pass


def _provider_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        return str(payload)[:240]
    except (ValueError, TypeError):
        return response.text[:240]


def _key() -> str:
    if not config.ELEVENLABS_API_KEY:
        raise ElevenLabsError("ElevenLabs API key is not configured")
    return config.ELEVENLABS_API_KEY.get_secret_value()


async def sound_effect(prompt: str) -> bytes:
    prompt = f"{prompt[:850]}. Pure instrumental/environmental sound effect only; no speech, no voices, no dialogue, no people talking. Generate only the requested natural environmental sound."
    client = await pooled_client(90)
    response = await client.post(
            "https://api.elevenlabs.io/v1/sound-generation",
            headers={"xi-api-key": _key(), "Accept": "audio/mpeg"},
            json={"text": prompt[:1000], "duration_seconds": 8, "prompt_influence": 1.0},
    )
    if response.status_code >= 400:
        raise ElevenLabsError("ElevenLabs sound generation failed")
    if not response.content:
        raise ElevenLabsError("ElevenLabs returned an empty sound effect")
    return response.content


async def isolate_audio(data: bytes, filename: str = "audio.mp3") -> bytes:
    data = bytes(data)
    client = await pooled_client(120)
    response = await client.post(
            "https://api.elevenlabs.io/v1/audio-isolation",
            headers={"xi-api-key": _key(), "Accept": "audio/mpeg"},
            files={"file": (filename, data, "application/octet-stream")},
    )
    if response.status_code >= 400:
        raise ElevenLabsError("ElevenLabs audio isolation failed")
    return response.content


async def speech_to_text(data: bytes, filename: str = "voice.m4a") -> dict:
    data = bytes(data)
    try:
        content_type = "audio/mp4" if filename.casefold().endswith((".m4a", ".mp4")) else "audio/ogg"
        client = await pooled_client(120)
        response = await client.post(
                "https://api.elevenlabs.io/v1/speech-to-text",
                headers={"xi-api-key": _key()},
                files={"file": (filename, data, content_type)},
                data={"model_id": "scribe_v1", "language_code": "ru"},
        )
        if response.status_code >= 400:
            logging.warning("ElevenLabs speech-to-text rejected status=%s detail=%s", response.status_code, _provider_detail(response))
            raise ElevenLabsError("ElevenLabs speech-to-text failed")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ElevenLabsError("ElevenLabs returned an invalid transcription response")
        return payload
    except ElevenLabsError:
        raise
    except (httpx.HTTPError, TimeoutError, ValueError) as exc:
        raise ElevenLabsError("ElevenLabs speech-to-text is temporarily unavailable") from exc


async def speech_to_speech(data: bytes, voice_id: str, filename: str = "voice.m4a") -> bytes:
    if not voice_id.strip():
        raise ElevenLabsError("ElevenLabs voice id is required")
    data = bytes(data)
    try:
        client = await pooled_client(180)
        response = await client.post(
                f"https://api.elevenlabs.io/v1/speech-to-speech/{voice_id}",
                headers={"xi-api-key": _key(), "Accept": "audio/mpeg"},
                files={"audio": (filename, data, "application/octet-stream")},
                data={"model_id": "eleven_multilingual_sts_v2"},
        )
        if response.status_code >= 400:
            raise ElevenLabsError("ElevenLabs speech-to-speech failed")
        if not response.content:
            raise ElevenLabsError("ElevenLabs returned an empty speech-to-speech response")
        return response.content
    except ElevenLabsError:
        raise
    except (httpx.HTTPError, TimeoutError) as exc:
        raise ElevenLabsError("ElevenLabs speech-to-speech is temporarily unavailable") from exc


async def list_voices() -> dict:
    try:
        client = await pooled_client(30)
        response = await client.get("https://api.elevenlabs.io/v2/voices", headers={"xi-api-key": _key()})
        if response.status_code >= 400:
            raise ElevenLabsError("ElevenLabs voices lookup failed")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ElevenLabsError("ElevenLabs returned an invalid voices response")
        return payload
    except ElevenLabsError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise ElevenLabsError("ElevenLabs voices lookup is temporarily unavailable") from exc


async def list_models() -> list:
    try:
        client = await pooled_client(30)
        response = await client.get("https://api.elevenlabs.io/v1/models", headers={"xi-api-key": _key()})
        if response.status_code >= 400:
            raise ElevenLabsError("ElevenLabs models lookup failed")
        payload = response.json()
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            models = payload.get("models")
            return models if isinstance(models, list) else [payload]
        raise ElevenLabsError("ElevenLabs returned an invalid models response")
    except ElevenLabsError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise ElevenLabsError("ElevenLabs models lookup is temporarily unavailable") from exc


async def design_voice(description: str) -> dict:
    description = description.strip()
    if not description:
        raise ElevenLabsError("voice description is required")
    if len(description) < 20:
        raise ElevenLabsError("Опиши голос подробнее: минимум 20 символов")
    try:
        # Voice Design can take a while, but an unbounded provider request
        # leaves both Telegram and the mobile client waiting forever.
        client = await pooled_client(40)
        response = await client.post(
            "https://api.elevenlabs.io/v1/text-to-voice/design",
            headers={"xi-api-key": _key(), "Content-Type": "application/json"},
            json={"voice_description": description[:1000], "auto_generate_text": True},
        )
        logging.info("ElevenLabs voice design response status=%s", response.status_code)
        if response.status_code >= 400:
            logging.warning("ElevenLabs voice design rejected status=%s detail=%s", response.status_code, _provider_detail(response))
            if response.status_code == 403 and "blocked_generation" in _provider_detail(response):
                raise ElevenLabsError("Я не могу копировать голос конкретного человека. Опиши желаемые характеристики без имени: например, низкий, спокойный мужской голос с кавказским акцентом.")
            raise ElevenLabsError("ElevenLabs voice generation failed")
        payload = response.json()
        logging.info("ElevenLabs voice design response keys=%s", sorted(payload.keys())[:20] if isinstance(payload, dict) else type(payload).__name__)
        if not isinstance(payload, dict):
            raise ElevenLabsError("ElevenLabs returned an invalid voice response")

        # The current API returns a generated_voice_id inside previews.
            # Turn that preview into a persistent voice before returning it to
            # clients; the preview id is not suitable for speech-to-speech.
        previews = payload.get("previews")
        preview = previews[0] if isinstance(previews, list) and previews else None
        generated_id = preview.get("generated_voice_id") if isinstance(preview, dict) else None
        if generated_id and not (payload.get("voice_id") or payload.get("id")):
            created = await client.post(
                    "https://api.elevenlabs.io/v1/text-to-voice",
                    headers={"xi-api-key": _key(), "Content-Type": "application/json"},
                    json={
                        "voice_name": "ALTER voice",
                        "voice_description": description[:1000],
                        "generated_voice_id": generated_id,
                    },
            )
            logging.info("ElevenLabs voice persist response status=%s", created.status_code)
            if created.status_code >= 400:
                logging.warning("ElevenLabs voice persist rejected status=%s detail=%s", created.status_code, _provider_detail(created))
                raise ElevenLabsError("ElevenLabs voice creation failed")
            created_payload = created.json()
            logging.info("ElevenLabs voice persist response keys=%s", sorted(created_payload.keys())[:20] if isinstance(created_payload, dict) else type(created_payload).__name__)
            if not isinstance(created_payload, dict):
                raise ElevenLabsError("ElevenLabs returned an invalid created voice response")
            return {**payload, **created_payload}
        return payload
    except ElevenLabsError:
        raise
    except (httpx.HTTPError, TimeoutError, ValueError) as exc:
        raise ElevenLabsError("ElevenLabs voice generation is temporarily unavailable") from exc
