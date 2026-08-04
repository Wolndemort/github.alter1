import asyncio
import tempfile
from pathlib import Path


async def video_preview(data: bytes) -> list[tuple[str, bytes]]:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "input.mp4"
        output = Path(directory) / "frame-%02d.jpg"
        source.write_bytes(data)
        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", str(source), "-vf", "fps=1/5,scale=960:-1", "-frames:v", "6", str(output),
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
