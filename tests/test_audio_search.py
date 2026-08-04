import asyncio
import sys
import types
from pathlib import Path

from utils import audio_search


def run(coro):
    return asyncio.run(coro)


def test_download_audio_returns_mp3_and_title(monkeypatch, tmp_path):
    captured = {}

    class YoutubeDL:
        def __init__(self, options):
            captured["options"] = options
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download=True):
            Path(captured["options"]["outtmpl"].replace("%(ext)s", "mp3")).write_bytes(b"audio")
            assert url == "https://youtube.com/watch?v=1"
            assert download is True
            return {"title": "Demo song"}

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=YoutubeDL))
    monkeypatch.setattr(audio_search.tempfile, "mkdtemp", lambda prefix: str(tmp_path))
    result = run(audio_search.download_audio("https://youtube.com/watch?v=1"))
    assert result is not None
    path, title = result
    assert path.suffix == ".mp3"
    assert title == "Demo song"
    assert captured["options"]["postprocessors"][0]["preferredquality"] == "192"


def test_download_audio_returns_none_on_provider_error(monkeypatch, tmp_path):
    class YoutubeDL:
        def __init__(self, options): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, *args, **kwargs): raise RuntimeError("download failed")
    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=YoutubeDL))
    monkeypatch.setattr(audio_search.tempfile, "mkdtemp", lambda prefix: str(tmp_path))
    assert run(audio_search.download_audio("bad-url")) is None


def test_remove_audio_deletes_file_and_directory(tmp_path):
    directory = tmp_path / "audio"
    directory.mkdir()
    audio = directory / "audio.mp3"
    audio.write_bytes(b"audio")
    audio_search.remove_audio(audio)
    assert not audio.exists()
    assert not directory.exists()


def test_remove_audio_accepts_none():
    audio_search.remove_audio(None)


def test_audio_contract_uses_ffmpeg_and_size_limit():
    source = Path("utils/audio_search.py").read_text(encoding="utf-8")
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "FFmpegExtractAudio" in source
    assert "50 * 1024 * 1024" in source
    assert "ffmpeg" in dockerfile
