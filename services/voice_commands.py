"""Natural-language routing for user-facing ElevenLabs voice actions."""
from __future__ import annotations

import re


def is_voice_generation_request(text: str) -> bool:
    value = (text or "").casefold()
    return bool(re.search(r"\b(?:создай|сгенерируй|сделай)\b.*\bголос\b", value))


def is_voice_change_request(text: str) -> bool:
    value = (text or "").casefold()
    return bool(re.search(r"\b(?:измени|поменяй|преобразуй|сделай)\b.*\b(?:мой|этот)?\s*голос\b", value))


def voice_description(text: str) -> str:
    value = re.sub(r"^\s*(?:создай|сгенерируй|сделай)\s+(?:мне\s+)?голос\s*", "", text or "", flags=re.IGNORECASE)
    return value.strip(" .,!?:;")


def requested_voice_id(text: str, saved_voice_id: str | None, default_voice_id: str | None) -> str | None:
    explicit = re.search(r"\bvoice[_ -]?id\s*=\s*([A-Za-z0-9_-]{6,})\b", text or "", flags=re.IGNORECASE)
    match = explicit or re.search(r"\bголос(?:ом)?\s+([A-Za-z0-9_-]{6,})\b", text or "", flags=re.IGNORECASE)
    return match.group(1) if match else saved_voice_id or default_voice_id
