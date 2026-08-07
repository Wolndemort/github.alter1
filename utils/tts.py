import asyncio
import base64
import logging
import tempfile
import wave
from io import BytesIO
from pathlib import Path

from config import config
from utils.ap_logic import client
from utils.metrics import increment


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


async def synthesize_speech(text: str, voice: str | None = None, output_format: str = "ogg") -> bytes:
    """Generate OGG/Opus via OpenRouter's documented audio chat response."""
    try:
        response = await client.chat.completions.create(
            model=config.TTS_MODEL,
            modalities=["text", "audio"],
            audio={"voice": voice or config.TTS_VOICE, "format": "pcm16"},
            messages=[
                {"role": "system", "content": "Read the user's text exactly as written. Do not summarize, paraphrase, add, remove, or reinterpret any words."},
                {"role": "user", "content": text[:config.TTS_MAX_CHARS]},
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
