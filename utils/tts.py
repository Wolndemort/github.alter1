import asyncio
import base64
import logging
import re
import tempfile
import wave
from io import BytesIO
from pathlib import Path
import httpx

from config import config
from utils.ap_logic import client
from utils.metrics import increment
from utils.quality import sanitize_public_reply


def _get_audio_data(response) -> bytes:
    message = response.choices[0].message
    audio = getattr(message, "audio", None)
    if isinstance(audio, dict):
        data = audio.get("data")
    else:
        data = getattr(audio, "data", None)
    return base64.b64decode(data) if data else b""


async def _get_stream_audio_data(response) -> bytes:
    """Collect base64 audio fragments returned by OpenRouter streaming TTS."""
    chunks = []
    async for chunk in response:
        choices = getattr(chunk, "choices", []) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        audio = getattr(delta, "audio", None) if delta else None
        if isinstance(audio, dict):
            data = audio.get("data")
        else:
            data = getattr(audio, "data", None)
        if data:
            chunks.append(data)
    return base64.b64decode("".join(chunks)) if chunks else b""


async def _wav_to_ogg(wav: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "input.wav"
        target = Path(directory) / "output.ogg"
        source.write_bytes(wav)
        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", str(source), "-ac", "1", "-c:a", "libopus",
                "-b:a", "32k", str(target), stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await process.communicate()
            if process.returncode != 0:
                return b""
        except (FileNotFoundError, OSError):
            return b""
        return target.read_bytes() if target.exists() else b""


def _pcm16_to_wav(pcm: bytes, sample_rate: int = 24000) -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(pcm)
    return output.getvalue()


def _prepare_tts_text(text: str) -> str:
    """Prepare visible text for speech without sending links or markup aloud."""
    value = re.sub(r"```[^`]*```", "", sanitize_public_reply(text), flags=re.DOTALL)
    value = re.sub(r"https?://\S+", "ссылка", value)
    value = re.sub(r"\s+", " ", value).strip()
    return re.sub(r"\bALTER\b", "А́льтер", value, flags=re.IGNORECASE)[:config.TTS_MAX_CHARS]


async def synthesize_speech(text: str, voice: str | None = None, output_format: str = "ogg") -> bytes:
    """Generate speech with ElevenLabs when enabled, falling back to OpenRouter."""
    logging.info("TTS voice request selected=%s", voice or config.TTS_VOICE)
    if voice == "elevenlabs" and not (
        config.ELEVENLABS_ENABLED and config.ELEVENLABS_API_KEY and config.ELEVENLABS_VOICE_ID
    ):
        logging.error(
            "ElevenLabs voice selected but configuration is incomplete: enabled=%s key=%s voice_id=%s",
            config.ELEVENLABS_ENABLED,
            bool(config.ELEVENLABS_API_KEY),
            bool(config.ELEVENLABS_VOICE_ID),
        )
        return b""
    # The provider is a user-selectable voice option.  Do not silently use
    # ElevenLabs for every voice whenever its global credentials are present;
    # otherwise switching between OpenRouter voices and Premium sounds the
    # same and the mobile setting appears broken.
    if voice == "elevenlabs" and config.ELEVENLABS_ENABLED and config.ELEVENLABS_API_KEY and config.ELEVENLABS_VOICE_ID:
        try:
            voice_id = config.ELEVENLABS_VOICE_ID
            async with httpx.AsyncClient(timeout=45) as eleven_client:
                response = await eleven_client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    headers={"xi-api-key": config.ELEVENLABS_API_KEY.get_secret_value(), "Accept": "audio/pcm"},
                    params={"output_format": "pcm_24000"},
                    json={
                        "text": _prepare_tts_text(text),
                        "model_id": config.ELEVENLABS_MODEL or "eleven_multilingual_v2",
                        "voice_settings": {"stability": 0.58, "similarity_boost": 0.82, "style": 0.08, "use_speaker_boost": True},
                    },
                )
                response.raise_for_status()
                pcm = response.content
            wav = _pcm16_to_wav(pcm, 24000)
            result = await _wav_to_ogg(wav) if output_format == "ogg" else wav
            if result:
                increment("voice.tts.elevenlabs.success")
                return result
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 402:
                logging.error("ElevenLabs Premium rejected TTS: payment/credits required (HTTP 402)")
            else:
                logging.exception("ElevenLabs Premium TTS failed with HTTP %s", exc.response.status_code)
            return b""
        except Exception:
            logging.exception("ElevenLabs speech synthesis failed for explicitly selected Premium voice")
            return b""
    try:
        provider_voice = config.TTS_VOICE if voice == "elevenlabs" else (voice or config.TTS_VOICE)
        # Make the brand pronunciation unambiguous for Russian speech models:
        # ALTER is the assistant's name, pronounced "А́льтер".
        spoken_text = _prepare_tts_text(text)
        response = await client.chat.completions.create(
            model=config.TTS_MODEL,
            modalities=["text", "audio"],
            audio={"voice": provider_voice, "format": "pcm16"},
            messages=[
                {"role": "system", "content": "Прочитай пользовательский текст дословно на русском языке. Не пересказывай, не сокращай, не добавляй и не объясняй его. Название ALTER произноси как «А́льтер»."},
                {"role": "user", "content": spoken_text[:config.TTS_MAX_CHARS]},
            ],
            # Keep voice replies understandable without allowing huge audio output.
            max_tokens=config.TTS_MAX_TOKENS,
            stream=True,
        )
        pcm = await _get_stream_audio_data(response)
        wav = _pcm16_to_wav(pcm) if pcm else b""
        result = (await _wav_to_ogg(wav) if output_format == "ogg" else wav) if wav else b""
        increment("voice.tts.success" if result else "voice.tts.empty")
        return result
    except Exception:
        increment("voice.tts.failure")
        logging.exception("Speech synthesis error")
        return b""
