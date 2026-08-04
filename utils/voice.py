import logging
from utils.metrics import timer

from config import config
from utils.ap_logic import client


async def transcribe_voice(data: bytes) -> str:
    metric = timer("voice_transcription")
    try:
        result = await client.audio.transcriptions.create(
            model=config.TRANSCRIPTION_MODEL,
            file=("voice.ogg", data),
            language="ru",
        )
        text = (result.text or "").strip()
        metric(size=len(data), result="ok")
        return text
    except Exception:
        logging.exception("Voice transcription error")
        metric(size=len(data), result="error")
        return ""
