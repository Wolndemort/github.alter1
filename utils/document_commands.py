"""Shared, auditable natural-language document edit command normalization.

The parser deliberately produces the small, deterministic ``old => new``
language consumed by :func:`services.document_ingestion.edit_document`.
Telegram captions, mobile prompts and API clients therefore follow exactly
the same edit semantics.
"""
from __future__ import annotations

import re


_EDIT_VERBS = (
    r"(?:/edit|измени(?:ть)?|поменяй(?:ть)?|замени(?:ть)?|исправь(?:ть)?|"
    r"редактируй(?:ть)?|переделай(?:ть)?|переформатируй(?:ть)?|"
    r"replace|change|edit|correct|update|rewrite)"
)
_REMOVE_VERBS = r"(?:убери|удали|исключи|удалить|remove|delete|drop)"
_ADD_VERBS = r"(?:добавь|вставь|добавить|вставить|add|insert)"
_DOCUMENT_TAIL = r"(?:\s+(?:в|из|для)\s+(?:этом\s+)?(?:документ\w*|файл\w*|pdf|document|file))?\s*$"


_ARTIFACT_REFERENCE = r"(?:(?:the\s+)?(?:last|previous)\s+(?:(?:created|generated)\s+)?(?:document|file|result|artifact)|(?:\u043f\u043e\u0441\u043b\u0435\u0434\u043d\w*|\u043f\u0440\u0435\u0434\u044b\u0434\u0443\u0449\w*)\s+(?:(?:\u0441\u043e\u0437\u0434\u0430\u043d\w*|\u0441\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u043d\w*)\s+)?(?:\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\w*|\u0444\u0430\u0439\u043b\w*|\u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\w*|\u0430\u0440\u0442\u0435\u0444\u0430\u043a\u0442\w*))"


def _text(value: str) -> str:
    value = str(value or "")
    # A few old integrations sent UTF-8 decoded as latin-1. Keep the
    # compatibility path, but never apply it to normal Cyrillic input.
    try:
        return value.encode("latin1").decode("utf-8") if "Р" in value else value
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _clean(value: str) -> str:
    value = re.sub(r"^\s*(?:пожалуйста|please|можешь|можно|could you)\s*[, :]?\s*", "", value, flags=re.I)
    value = re.sub(r"\s+(?:в|из|для)\s+(?:этом\s+)?(?:документ\w*|файл\w*|pdf|document|file)\s*$", "", value, flags=re.I)
    return value.strip(" \t\r\n.,;:")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] in "\"'«“[" and value[-1] in "\"'»”]":
        return value[1:-1].strip()
    return value


def _explicit(value: str) -> str | None:
    if "=>" not in value:
        return None
    lines = []
    for line in value.splitlines():
        if "=>" not in line:
            continue
        old, new = line.split("=>", 1)
        old, new = _unquote(old.strip()), _unquote(new.strip())
        if old:
            lines.append(f"{old} => {new}")
    return "\n".join(lines) or None


def document_edit_instruction(prompt: str) -> str:
    """Normalize Russian/English edit requests into explicit replacements.

    Supported examples include ``замени старый на новый``, ``удали X``,
    ``добавь Y после X``, ``replace X with Y`` and explicit ``X => Y``.
    The result is intentionally not inferred by an LLM, so exports remain
    reviewable and safe.
    """
    value = _text(prompt).strip()
    value = re.sub(r"^\s*alter\s*[:,-]?\s*", "", value, flags=re.I)
    value = re.sub(r"^\s*/edit\s*", "", value, flags=re.I)
    value = _clean(value)
    value = re.sub(rf"^\s*{_EDIT_VERBS}\s*[:, -]?\s*", "", value, flags=re.I)
    value = _clean(value)
    value = re.sub(rf"^\s*{_ARTIFACT_REFERENCE}\s*[:,-]\s*", "", value, flags=re.I)
    value = _clean(value)
    explicit = _explicit(value)
    if explicit:
        return explicit

    # English commands commonly use quoted values and a trailing file
    # qualifier ("in the PDF").  Strip that qualifier before matching so it
    # cannot become part of the replacement value.
    value = re.sub(r"\s+in\s+(?:the\s+)?(?:document|file|pdf)\s*$", "", value, flags=re.I)
    match = re.match(r"^(.+?)\s+(?:на|на место|with|to)\s+(.+?)\s*$", value, flags=re.I)
    if match:
        return f"{_unquote(match.group(1))} => {_unquote(match.group(2))}"
    match = re.match(r"^(.+?)\s+(?:замени|replace)\s+на\s+(.+)$", value, flags=re.I)
    if match:
        return f"{_unquote(match.group(1))} => {_unquote(match.group(2))}"

    match = re.match(rf"^\s*{_REMOVE_VERBS}\s+(.+?){_DOCUMENT_TAIL}", value, flags=re.I)
    if match:
        return f"{_unquote(match.group(1))} =>"

    match = re.match(rf"^\s*{_ADD_VERBS}\s+(.+?)\s+(после|перед|after|before)\s+(.+?){_DOCUMENT_TAIL}", value, flags=re.I)
    if match:
        addition, position, anchor = (_unquote(item.strip()) for item in match.groups())
        return f"{anchor} => {anchor} {addition}" if position.casefold() in {"после", "after"} else f"{anchor} => {addition} {anchor}"

    # Keep an explicit verb in the final error instead of silently treating a
    # vague request like "сделай красиво" as a destructive edit.
    return value


def is_document_edit_request(prompt: str) -> bool:
    value = _text(prompt).strip()
    value = re.sub(r"^\s*alter\s*[:,-]?\s*", "", value, flags=re.I)
    value = re.sub(r"^\s*(?:please|можешь|можно|could you)\s*[, :]?\s*", "", value, flags=re.I)
    value = " ".join(value.casefold().split())
    return bool(
        "=>" in value
        or re.match(rf"^(?:{_EDIT_VERBS}|{_REMOVE_VERBS}|{_ADD_VERBS})\b", value, flags=re.I)
    )
