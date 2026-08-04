import asyncio
import os
import tempfile
from pathlib import Path


async def download_audio(url: str) -> tuple[Path, str] | None:
    """Download a YouTube result as a Telegram-compatible MP3."""
    directory = Path(tempfile.mkdtemp(prefix="alter-audio-"))
    output = directory / "audio.%(ext)s"
    options = {
        "format": "bestaudio/best",
        "outtmpl": str(output),
        "noplaylist": True,
        "max_filesize": 50 * 1024 * 1024,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        "quiet": True,
        "no_warnings": True,
    }
    try:
        def run():
            import yt_dlp
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                return info.get("title", "ALTER audio")
        title = await asyncio.to_thread(run)
        files = list(directory.glob("audio.*"))
        audio = next((item for item in files if item.suffix == ".mp3"), None)
        return (audio, title) if audio else None
    except Exception:
        return None


def remove_audio(audio: Path | None) -> None:
    if audio:
        try:
            directory = audio.parent
            audio.unlink(missing_ok=True)
            directory.rmdir()
        except OSError:
            pass
