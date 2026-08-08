"""Natural-language audio actions shared by Telegram and the mobile API."""
from __future__ import annotations

import asyncio
import re
import tempfile
from pathlib import Path

from services.elevenlabs_media import isolate_audio, sound_effect


def detect_audio_action(text: str) -> str | None:
    value = (text or "").casefold()
    if any(word in value for word in ("наложи", "добавь", "смешай", "подложи", "фоновой звук")) and any(
        word in value for word in ("голос", "голосовое", "аудио", "запись")
    ):
        return "mix"
    if any(word in value for word in ("почисти", "очисти", "убери шум", "убрать шум", "изоляц", "отдели голос")):
        return "isolate"
    if any(word in value for word in ("создай звук", "сгенерируй звук", "сделай звук", "звуковой эффект", "саунд эффект")):
        return "effect"
    return None


def effect_prompt(text: str) -> str:
    value = re.sub(r"[,.!?;:]+", " ", text or "")
    value = re.sub(
        r"\b(?:наложи|добавь|смешай|подложи|создай|сгенерируй|сделай|звук|звуковой|эффект|саунд|на|к|мо[её]|мое|моём|голосовое|голос|аудио|запись|из|под|фон)\b",
        " ", value, flags=re.IGNORECASE,
    )
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value or "спокойный атмосферный звук дождя"


async def mix_audio(source: bytes, effect: bytes, source_name: str = "voice.m4a") -> bytes:
    """Mix an uploaded recording with a generated effect and return MP3."""
    with tempfile.TemporaryDirectory(prefix="alter-audio-") as directory:
        source_path = Path(directory) / source_name
        effect_path = Path(directory) / "effect.mp3"
        output_path = Path(directory) / "alter-mix.mp3"
        source_path.write_bytes(source)
        effect_path.write_bytes(effect)
        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", str(source_path), "-i", str(effect_path),
                "-filter_complex", "[0:a]volume=1[a0];[1:a]volume=0.28[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[out]",
                "-map", "[out]", "-ac", "1", "-b:a", "128k", str(output_path),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
        except (FileNotFoundError, OSError) as exc:
            raise RuntimeError("ffmpeg is required for audio mixing") from exc
        if process.returncode != 0 or not output_path.exists():
            raise RuntimeError(f"audio mixing failed: {stderr.decode(errors='replace')[-300:]}")
        return output_path.read_bytes()


async def process_audio_action(prompt: str, data: bytes, filename: str = "voice.m4a") -> tuple[str, bytes] | None:
    """Run an explicitly requested audio operation, or return None for normal chat."""
    action = detect_audio_action(prompt)
    if not action:
        return None
    if action == "effect":
        return "Создал звуковой эффект.", await sound_effect(effect_prompt(prompt))
    if action == "isolate":
        return "Почистил запись и изолировал голос.", await isolate_audio(data, filename)
    effect = await sound_effect(effect_prompt(prompt))
    return "Наложил звуковой эффект на голосовое.", await mix_audio(data, effect, filename)
