"""Natural-language routing for real Fal.ai generation requests."""
from __future__ import annotations

import re


_IMAGE_PATTERNS = (
    r"\bсоздай\b.*\b(?:фото|фотографи|изображени|картин)",
    r"\bсгенерируй\b.*\b(?:фото|фотографи|изображени|картин)",
    r"\bнарисуй\b", r"\bсделай\b.*\b(?:фото|фотографи|изображени|картин)",
)
_VIDEO_PATTERNS = (
    r"\bсоздай\b.*\b(?:видео|ролик)", r"\bсгенерируй\b.*\b(?:видео|ролик)",
    r"\bоживи\b", r"\bсделай\b.*\b(?:видео|ролик)",
)


def generation_kind(text: str) -> str | None:
    value = (text or "").casefold().replace("ё", "е")
    if any(re.search(pattern, value) for pattern in _VIDEO_PATTERNS):
        return "video"
    if any(re.search(pattern, value) for pattern in _IMAGE_PATTERNS):
        return "image"
    return None
