"""Natural-language routing for user-facing ElevenLabs voice actions."""
from __future__ import annotations
import re

def _text(value: str) -> str:
    value = value or ""
    try:
        return value.encode("latin1").decode("utf-8") if "Р" in value else value
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value

def is_voice_generation_request(text: str) -> bool:
    value = re.sub(r"\s+", " ", _text(text).casefold()).strip()
    verbs = r"(?:создай\w*|сгенерируй\w*|сделай\w*|придумай\w*|получи\w*|хочу|нужен|create|generate|make|get|design)"
    noun = r"(?:голос\w*|озвучк\w*|озвучивани\w*|диктор\w*|персонажн\w*\s+голос\w*|voice\w*)"
    return bool(re.search(rf"\b{verbs}\b.*\b{noun}\b|\b(?:новый|свой|персонажный|custom|new)\s+{noun}\b", value))

def is_voice_change_request(text: str) -> bool:
    value = re.sub(r"\s+", " ", _text(text).casefold()).strip()
    verbs = r"(?:измени\w*|поменяй\w*|переделай\w*|преобразуй\w*|обработай\w*|замени\w*|сделай\s+другим|change|replace|convert|transform)"
    return bool(re.search(rf"\b{verbs}\b.*\b(?:мой|этот|свой|созданн\w*|custom|my)?\s*голос\w*\b|\b(?:озвучь|speak)\b.*\b(?:этим|другим|созданн\w*|custom)\s+голос\w*", value))

def voice_description(text: str) -> str:
    value = re.sub(r"^\s*(?:создай\w*|сгенерируй\w*|сделай\w*|придумай\w*|получи\w*|хочу|create|generate|make|get|design)\s+(?:мне\s+)?(?:новый\s+|свой\s+|custom\s+|new\s+)?(?:голос\w*|voice)\s*[:,-]?\s*", "", _text(text), flags=re.IGNORECASE)
    return value.strip(" .,!?:;")

def requested_voice_id(text: str, saved_voice_id: str | None, default_voice_id: str | None) -> str | None:
    text = _text(text)
    explicit = re.search(r"\bvoice[_ -]?id\s*=\s*([A-Za-z0-9_-]{6,})\b", text, flags=re.IGNORECASE)
    match = explicit or re.search(r"\bголос(?:ом)?\s+([A-Za-z0-9_-]{6,})\b", text, flags=re.IGNORECASE)
    return match.group(1) if match else saved_voice_id or default_voice_id
