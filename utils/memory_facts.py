"""Deterministic extraction of high-value user facts."""

from __future__ import annotations

import re


_VEHICLE_PATTERNS = (
    re.compile(r"\b(?:у\s+меня|моя|мой)\s+(?:машина|авто|тачка)\s*(?:это|[-:])?\s*(?P<value>[^.!?\n]{2,120})", re.I),
    re.compile(r"\b(?:машина|авто|тачка)\s+(?:у\s+меня\s+)?(?:это\s+)?(?P<value>[A-Za-zА-Яа-я0-9][^.!?\n]{1,119})", re.I),
)

# Keep explicit, high-confidence facts available immediately to every client.
# The legacy patterns above are retained for backward compatibility with old
# stored/test data, but these patterns match normal UTF-8 Russian input.
_EXPLICIT_PATTERNS = (
    (re.compile(r"\b(?:меня зовут|моё имя|мое имя)\s+(?P<value>[^.!?\n]{2,80})", re.I), "identity", "name"),
    (re.compile(r"\b(?:я живу в|я из)\s+(?P<value>[^.!?\n]{2,80})", re.I), "identity", "city"),
    (re.compile(r"\b(?:я работаю|моя работа|моя профессия)\s+(?:в|—|-)?\s*(?P<value>[^.!?\n]{2,120})", re.I), "skills_career", "job"),
    (re.compile(r"\b(?:я изучаю|я учусь|моя цель)\s+(?P<value>[^.!?\n]{2,120})", re.I), "goals_habits", "focus"),
    (re.compile(r"\b(?:мне нравится|я люблю|я предпочитаю)\s+(?P<value>[^.!?\n]{2,120})", re.I), "preferences", "likes"),
)


def extract_user_facts(text: str) -> dict:
    value = " ".join(str(text or "").split()).strip(" .,!?:;-\n\t")
    for pattern, category, key in _EXPLICIT_PATTERNS:
        match = pattern.search(value)
        if match:
            fact = match.group("value").strip(" .,!?:;-\n\t")
            if fact:
                return {category: {key: fact[:120]}}
    for pattern in _VEHICLE_PATTERNS:
        match = pattern.search(value)
        if match:
            vehicle = match.group("value").strip(" .,!?:;-\n\t")
            if vehicle:
                return {"preferences": {"vehicle": vehicle[:120]}}
    return {}
