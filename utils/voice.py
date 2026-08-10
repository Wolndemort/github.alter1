import logging
from utils.metrics import timer

from config import config
from utils.ap_logic import client
from utils.metrics import increment


async def transcribe_voice(data: bytes) -> str:
    metric = timer("voice_transcription")
    try:
        result = await client.audio.transcriptions.create(
            model=config.TRANSCRIPTION_MODEL,
            # Expo iOS records AAC in an m4a container. The previous .ogg
            # filename made the provider reject otherwise valid audio bytes.
            file=("voice.m4a", data),
            language="ru",
            prompt="Русская речь. Распознавай слова точно, сохраняя имена, числа и знаки препинания. Не добавляй пояснений.",
        )
        text = (result.text or "").strip()
        metric(size=len(data), result="ok")
        increment("voice.transcription.success")
        return text
    except Exception:
        logging.exception("Voice transcription error")
        increment("voice.transcription.failure")
        metric(size=len(data), result="error")
        return ""
