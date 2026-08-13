"""Shared natural-language document edit command normalization."""
from __future__ import annotations

import re


def _text(value: str) -> str:
    value = value or ""
    try:
        return value.encode("latin1").decode("utf-8") if "Р" in value else value
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def is_document_edit_request(prompt: str) -> bool:
    value = re.sub(r"^\s*alter\s*[:,-]?\s*", "", _text(prompt), flags=re.IGNORECASE)
    value = " ".join(value.casefold().split())
    return bool("=>" in value or re.match(r"^(?:/edit|измени(?:ть)?|поменяй(?:ть)?|замени(?:ть)?|исправь(?:ть)?|редактируй(?:ть)?|убери|удали|добавь)\b", value))


def document_edit_instruction(prompt: str) -> str:
    value = re.sub(r"^\s*alter\s*[:,-]?\s*", "", _text(prompt), flags=re.IGNORECASE).strip()
    if "=>" in value:
        return value[5:].strip() if value.casefold().startswith("/edit") else value
    value = re.sub(r"^\s*(?:/edit|измени(?:ть)?|поменяй(?:ть)?|замени(?:ть)?|исправь(?:ть)?|редактируй(?:ть)?)\s*", "", value, flags=re.IGNORECASE)
    match = re.match(r"^(.+?)\s+на\s+(.+?)\s*$", value, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1).strip()} => {match.group(2).strip()}"
    match = re.match(r"^(?:убери|удали)\s+(.+?)\s*$", value, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1).strip()} =>"
    match = re.match(r"^добавь\s+(.+?)\s+(после|перед)\s+(.+?)\s*$", value, flags=re.IGNORECASE)
    if match:
        addition, position, anchor = (item.strip() for item in match.groups())
        return f"{anchor} => {anchor} {addition}" if position.casefold() == "после" else f"{anchor} => {addition} {anchor}"
    return value
