"""Structured, provider-agnostic contracts for video and music analysis."""
from __future__ import annotations

import re


def video_context(*, duration_seconds: float | None, frame_count: int, transcript: str = "") -> dict:
    duration = max(0.0, float(duration_seconds or 0))
    return {
        "duration_seconds": duration,
        "frame_count": max(0, int(frame_count)),
        "transcript_chars": len(transcript or ""),
        "coverage": min(1.0, (frame_count * 5) / duration) if duration else 0.0,
        "requires_more_sampling": bool(duration > 30 and frame_count < duration / 10),
    }


def music_analysis_contract(transcript: str = "") -> dict:
    """Stable result shape for music/audio models; absent facts stay empty."""
    return {
        "title": "",
        "artist": "",
        "language": "",
        "genre": [],
        "mood": [],
        "instruments": [],
        "tempo_bpm": None,
        "structure": [],
        "lyrics_excerpt": (transcript or "")[:4000],
        "timestamps": [],
        "confidence": 0.0,
        "uncertainty": ["audio analysis provider has not confirmed metadata"],
    }


def parse_music_timestamps(text: str) -> list[dict]:
    result = []
    for minute, second, label in re.findall(r"\[?(\d{1,2}):(\d{2})\]?\s*[-–—:]?\s*(.+)", text or ""):
        result.append({"at_seconds": int(minute) * 60 + int(second), "label": label.strip()[:200]})
    return result[:100]
