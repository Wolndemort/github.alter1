import asyncio
import tempfile
from pathlib import Path


async def video_preview(data: bytes, duration_seconds: float | None = None) -> list[tuple[str, bytes]]:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "input.mp4"
        output = Path(directory) / "frame-%02d.jpg"
        source.write_bytes(data)
        # Sample the whole clip instead of taking only the first 30 seconds.
        # For short clips this keeps roughly one frame per second; for longer
        # clips it spreads twelve frames across the complete duration.
        duration = max(0.0, float(duration_seconds or 0.0))
        if duration > 0:
            fps = min(1.0, max(1.0 / 12.0, 8.0 / duration))
            frame_limit = 12
        else:
            fps = 1.0 / 5.0
            frame_limit = 6
        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", str(source), "-vf", f"fps={fps:g},scale=960:-1", "-frames:v", str(frame_limit), str(output),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await process.communicate()
        except (FileNotFoundError, OSError):
            return []
        return [("image/jpeg", path.read_bytes()) for path in sorted(Path(directory).glob("frame-*.jpg"))]


async def video_audio(data: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "input.mp4"
        target = Path(directory) / "audio.ogg"
        source.write_bytes(data)
        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", str(source), "-vn", "-ac", "1", "-b:a", "32k", str(target),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await process.communicate()
            return target.read_bytes() if target.exists() else b""
        except (FileNotFoundError, OSError):
            return b""


async def video_duration(data: bytes) -> float | None:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "input.mp4"
        source.write_bytes(data)
        try:
            process = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(source),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            output, _ = await process.communicate()
            return float(output.decode().strip()) if output else None
        except (FileNotFoundError, OSError, ValueError):
            return None
