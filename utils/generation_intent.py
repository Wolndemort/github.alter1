"""Natural-language routing for image/video generation and editing.

This is shared by Telegram captions, transcribed voice and HTTP/mobile chat.
Analysis requests are intentionally excluded so an attached photo is not
sent to an expensive generation provider by accident.
"""
from __future__ import annotations

import re


_IMAGE_WORDS = r"(?:фото\w*|фотографи\w*|изображени\w*|картин\w*|портрет\w*|иллюстраци\w*|image|photo|picture|portrait)"
_VIDEO_WORDS = r"(?:видео\w*|ролик\w*|клип\w*|анимаци\w*|video|clip|animation|reel)"
_CREATE = r"(?:создай\w*|сгенерируй\w*|сделай\w*|нарисуй\w*|создать|сгенерировать|сделать|create|generate|make|draw|render)"
_EDIT = r"(?:измени\w*|переделай\w*|отредактируй\w*|редактируй\w*|убери\w*|добавь\w*|замени\w*|преобразуй\w*|стилизуй\w*|оживи\w*|анимируй\w*|edit|change|remove|add|replace|animate|stylize|transform)"
_ANALYSIS = r"(?:анализируй\w*|проанализируй\w*|опиши\w*|прочитай\w*|разбери\w*|распознай\w*|что\s+на|analy[sz]e|describe|read|extract)"


def _text(value: str) -> str:
    value = str(value or "")
    try:
        return value.encode("latin1").decode("utf-8") if "Р" in value else value
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def generation_kind(text: str) -> str | None:
    value = re.sub(r"\s+", " ", _text(text).casefold().replace("ё", "е")).strip()
    if not value:
        return None
    # Explicit image-to-video and animation language takes precedence.
    if re.search(r"(?:image|photo|изображени\w*|фото\w*)\s*(?:to|в|->)\s*(?:video|видео)|\b(?:оживи|анимируй|animate)\b", value):
        return "video"
    if re.search(rf"\b(?:{_CREATE}|{_EDIT})\b.*\b{_VIDEO_WORDS}\b|\b{_VIDEO_WORDS}\b.*\b(?:{_CREATE}|{_EDIT})\b", value):
        return "video"
    # A bare video request is safe to classify only when it contains an
    # imperative/creation signal; ordinary analysis remains chat/vision.
    if re.search(rf"\b(?:{_CREATE})\b.*\b{_VIDEO_WORDS}\b", value):
        return "video"
    if re.search(rf"\b(?:{_CREATE}|{_EDIT})\b.*\b{_IMAGE_WORDS}\b|\b{_IMAGE_WORDS}\b.*\b(?:{_CREATE}|{_EDIT})\b", value):
        return "image"
    if re.search(rf"\b(?:{_CREATE}|{_EDIT})\b", value) and not re.search(rf"\b{_ANALYSIS}\b", value):
        # "Нарисуй ..." and English "make it cinematic" with an attached
        # image have no media noun; the caller supplies the source type.
        if re.search(r"\b(?:нарисуй|draw|render|stylize|стилизуй|transform|преобразуй)\b", value):
            return "image"
    return None
