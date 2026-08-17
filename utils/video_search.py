"""Download small, user-requested YouTube videos for chat attachments."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from config import config


async def download_video(url: str) -> tuple[Path, str] | None:
    directory = Path(tempfile.mkdtemp(prefix="alter-video-"))
    output = directory / "video.%(ext)s"
    options = {
        "format": "best[ext=mp4][height<=720]/best[height<=720]/best",
        "outtmpl": str(output), "noplaylist": True,
        "max_filesize": config.TELEGRAM_MAX_MEDIA_BYTES,
        "merge_output_format": "mp4", "quiet": True, "no_warnings": True,
    }
    try:
        def run():
            import yt_dlp
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                return info.get("title", "ALTER video")
        title = await asyncio.to_thread(run)
        files = list(directory.glob("video.*"))
        video = next((item for item in files if item.suffix.lower() in {".mp4", ".webm", ".mkv"}), None)
        if video and video.stat().st_size <= config.TELEGRAM_MAX_MEDIA_BYTES:
            return video, title
    except Exception:
        pass
    remove_video(directory / "missing")
    return None


def remove_video(video: Path | None) -> None:
    if not video:
        return
    directory = video.parent
    try:
        for item in directory.iterdir():
            item.unlink(missing_ok=True)
        directory.rmdir()
    except OSError:
        pass
