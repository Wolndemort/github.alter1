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
    value = _text(text).casefold()
    verbs = r"(?:создай|сгенерируй|сделай|придумай|создать|сгенерировать|сделать|получи|получить|нужен|хочу|create|generate|make|get)"
    noun = r"(?:голос|озвучку|озвучивание|диктора|персонажный\s+голос|voice)"
    return bool(re.search(rf"\b{verbs}\b.*\b{noun}\b|\b(?:новый|свой|персонажный)\s+{noun}\b|\bнужен\s+{noun}\b", value))

def is_voice_change_request(text: str) -> bool:
    value = _text(text).casefold()
    verbs = r"(?:измени|изменить|поменяй|поменять|переделай|переделать|преобразуй|преобразовать|обработай|обработать|замени|заменить|сделай\s+другим)"
    return bool(re.search(rf"\b{verbs}\b.*\b(?:мой|этот|свой)?\s*голос\b|\bозвучь\b.*\b(?:этим|другим|созданным)\s+голосом\b", value))

def voice_description(text: str) -> str:
    value = re.sub(r"^\s*(?:создай|сгенерируй|сделай|придумай|получи|получить|create|generate|make|get)\s+(?:мне\s+)?(?:новый\s+)?(?:голос|voice)\s*", "", _text(text), flags=re.IGNORECASE)
    return value.strip(" .,!?:;")

def requested_voice_id(text: str, saved_voice_id: str | None, default_voice_id: str | None) -> str | None:
    text = _text(text)
    explicit = re.search(r"\bvoice[_ -]?id\s*=\s*([A-Za-z0-9_-]{6,})\b", text, flags=re.IGNORECASE)
    match = explicit or re.search(r"\bголос(?:ом)?\s+([A-Za-z0-9_-]{6,})\b", text, flags=re.IGNORECASE)
    return match.group(1) if match else saved_voice_id or default_voice_id
