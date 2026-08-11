import logging
import asyncio
from utils.metrics import timer

from services.elevenlabs_media import speech_to_text
from utils.metrics import increment


async def _normalize_audio(data: bytes) -> bytes:
    """Convert Expo's platform-dependent recording container to stable WAV."""
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
            "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        output, error = await asyncio.wait_for(process.communicate(data), timeout=20)
        if process.returncode == 0 and output:
            logging.info("voice audio normalized input_bytes=%s output_bytes=%s", len(data), len(output))
            return output
        logging.warning("voice audio normalization skipped returncode=%s detail=%s", process.returncode, error.decode(errors="ignore")[:180])
    except (OSError, asyncio.TimeoutError) as exc:
        logging.warning("voice audio normalization unavailable: %s", type(exc).__name__)
    return data


async def transcribe_voice(data: bytes) -> str:
    metric = timer("voice_transcription")
    try:
        normalized = await _normalize_audio(bytes(data))
        result = await speech_to_text(normalized, "voice.wav" if normalized != bytes(data) else "voice.m4a")
        text = str(result.get("text") or result.get("transcript") or "").strip()
        metric(size=len(data), result="ok")
        increment("voice.transcription.success")
        return text
    except Exception:
        logging.exception("Voice transcription error")
        increment("voice.transcription.failure")
        metric(size=len(data), result="error")
        return ""
