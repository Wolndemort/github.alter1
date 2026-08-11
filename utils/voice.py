import logging
from utils.metrics import timer

from services.elevenlabs_media import speech_to_text
from utils.metrics import increment


async def transcribe_voice(data: bytes) -> str:
    metric = timer("voice_transcription")
    try:
        result = await speech_to_text(bytes(data), "voice.m4a")
        text = str(result.get("text") or result.get("transcript") or "").strip()
        metric(size=len(data), result="ok")
        increment("voice.transcription.success")
        return text
    except Exception:
        logging.exception("Voice transcription error")
        increment("voice.transcription.failure")
        metric(size=len(data), result="error")
        return ""
