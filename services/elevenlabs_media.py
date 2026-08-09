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
            json={"text": prompt[:1000], "duration_seconds": 8},
        )
    if response.status_code >= 400:
        raise ElevenLabsError("ElevenLabs sound generation failed")
    if not response.content:
        raise ElevenLabsError("ElevenLabs returned an empty sound effect")
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


async def speech_to_text(data: bytes, filename: str = "voice.m4a") -> dict:
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": _key()},
            files={"file": (filename, data, "application/octet-stream")},
            data={"model_id": "scribe_v1", "language_code": "ru"},
        )
    if response.status_code >= 400:
        raise ElevenLabsError("ElevenLabs speech-to-text failed")
    return response.json()


async def speech_to_speech(data: bytes, voice_id: str, filename: str = "voice.m4a") -> bytes:
    if not voice_id.strip():
        raise ElevenLabsError("ElevenLabs voice id is required")
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            f"https://api.elevenlabs.io/v1/speech-to-speech/{voice_id}",
            headers={"xi-api-key": _key(), "Accept": "audio/mpeg"},
            files={"audio": (filename, data, "application/octet-stream")},
            data={"model_id": "eleven_multilingual_sts_v2"},
        )
    if response.status_code >= 400:
        raise ElevenLabsError("ElevenLabs speech-to-speech failed")
    return response.content


async def list_voices() -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get("https://api.elevenlabs.io/v2/voices", headers={"xi-api-key": _key()})
    if response.status_code >= 400:
        raise ElevenLabsError("ElevenLabs voices lookup failed")
    return response.json()


async def list_models() -> list:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get("https://api.elevenlabs.io/v1/models", headers={"xi-api-key": _key()})
    if response.status_code >= 400:
        raise ElevenLabsError("ElevenLabs models lookup failed")
    return response.json()


async def design_voice(description: str) -> dict:
    if not description.strip():
        raise ElevenLabsError("voice description is required")
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            "https://api.elevenlabs.io/v1/text-to-voice/design",
            headers={"xi-api-key": _key(), "Content-Type": "application/json"},
            json={"voice_description": description[:1000]},
        )
    if response.status_code >= 400:
        raise ElevenLabsError("ElevenLabs voice generation failed")
    return response.json()
