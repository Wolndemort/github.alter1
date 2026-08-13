"""Natural-language routing for image/video generation and editing."""
from __future__ import annotations

import re

_IMAGE_WORDS = r"(?:фото|фотографию|изображение|картинку|картинку|портрет|иллюстрацию)"
_VIDEO_WORDS = r"(?:видео|ролик|клип|анимацию)"
_CREATE = r"(?:создай|сгенерируй|сделай|нарисуй|создать|сгенерировать|сделать)"
_EDIT = r"(?:измени|изменить|переделай|переделать|отредактируй|редактируй|убери|добавь|замени|преобразуй|стилизуй|оживи)"


def _text(value: str) -> str:
    value = value or ""
    try:
        return value.encode("latin1").decode("utf-8") if "Р" in value else value
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def generation_kind(text: str) -> str | None:
    value = _text(text).casefold().replace("ё", "е")
    if re.search(rf"\b(?:{_CREATE}|{_EDIT})\b.*\b{_VIDEO_WORDS}\b|\bоживи\b", value):
        return "video"
    if re.search(rf"\b(?:{_CREATE}|{_EDIT})\b.*\b{_IMAGE_WORDS}\b|\bнарисуй\b|\b(?:убери|добавь|замени)\b", value):
        return "image"
    return None
