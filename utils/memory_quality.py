"""Quality gate for long-term user-specific memory."""
from __future__ import annotations

import re
from utils.memory_facts import extract_user_facts

_EXPLICIT = re.compile(r"\b(?:запомни|сохрани|запиши|учти|не забывай)\b", re.I)
_FIRST_PERSON = re.compile(r"\b(?:я|мне|мой|моя|мои|моё|у меня|для меня|я хочу|планирую|собираюсь)\b", re.I)
_QUESTION = re.compile(r"[?]|\b(?:кто|что|где|когда|почему|как|можно ли|найди|проверь|покажи|расскажи)\b", re.I)
_TRANSIENT = re.compile(r"\b(?:привет|добрый|спасибо|понятно|окей|ок|хорошо|сделай|создай|найди|поищи|покажи|скачай|напомни|запусти|удали)\b", re.I)
_THIRD_PERSON = re.compile(r"\b(?:он|она|они|его|её|их|у него|у неё|у них)\b", re.I)


def is_explicit_memory_request(text: str) -> bool:
    return bool(_EXPLICIT.search(text or ""))


def is_memory_worthy(text: str, source: str = "user_message") -> bool:
    value = " ".join(str(text or "").split()).strip()
    if len(value) < 20:
        return False
    if source != "user_message" or is_explicit_memory_request(value):
        return True
    if _QUESTION.search(value) or _TRANSIENT.search(value) or _THIRD_PERSON.search(value):
        return False
    return bool(_FIRST_PERSON.search(value) and extract_user_facts(value))


def memory_reason(text: str, source: str = "user_message") -> str:
    if is_memory_worthy(text, source): return "accepted"
    if source != "user_message": return "trusted_source"
    if is_explicit_memory_request(text): return "explicit"
    if _QUESTION.search(text or ""): return "question_or_lookup"
    if _THIRD_PERSON.search(text or ""): return "third_person"
    return "no_durable_user_fact"


def sanitize_summary(value: dict | None) -> dict:
    if not isinstance(value, dict): return {}
    def clean(item):
        if isinstance(item, dict): return {key: cleaned for key, raw in item.items() if (cleaned := clean(raw)) not in (None, "", [], {})}
        if isinstance(item, list): return [cleaned for raw in item if (cleaned := clean(raw)) not in (None, "", [], {})]
        if isinstance(item, str): return " ".join(item.split()).strip()[:1000] or None
        return item
    return clean(value) or {}
