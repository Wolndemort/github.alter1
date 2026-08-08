"""Small ElevenLabs media adapter used by HTTP and Telegram clients."""
from __future__ import annotations

import httpx

from config import config


class ElevenLabsError(RuntimeError):
    pass


def _key() -> str:
    if not config.ELEVENLABS_API_KEY:
        raise ElevenLabsError("ElevenLabs API key is not configured")
    return config.ELEVENLABS_API_KEY.get_secret_value()


async def sound_effect(prompt: str) -> bytes:
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            "https://api.elevenlabs.io/v1/sound-generation",
            headers={"xi-api-key": _key(), "Accept": "audio/mpeg"},
            json={"text": prompt[:1000]},
        )
    if response.status_code >= 400:
        raise ElevenLabsError("ElevenLabs sound generation failed")
    return response.content


async def isolate_audio(data: bytes, filename: str = "audio.mp3") -> bytes:
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            "https://api.elevenlabs.io/v1/audio-isolation",
            headers={"xi-api-key": _key(), "Accept": "audio/mpeg"},
            files={"file": (filename, data, "application/octet-stream")},
        )
    if response.status_code >= 400:
        raise ElevenLabsError("ElevenLabs audio isolation failed")
    return response.content
