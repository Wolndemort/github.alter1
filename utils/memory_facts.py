"""Deterministic extraction of high-value user facts."""

from __future__ import annotations

import re


_VEHICLE_PATTERNS = (
    re.compile(r"\b(?:у\s+меня|моя|мой)\s+(?:машина|авто|тачка)\s*(?:это|[-:])?\s*(?P<value>[^.!?\n]{2,120})", re.I),
    re.compile(r"\b(?:машина|авто|тачка)\s+(?:у\s+меня\s+)?(?:это\s+)?(?P<value>[A-Za-zА-Яа-я0-9][^.!?\n]{1,119})", re.I),
)


def extract_user_facts(text: str) -> dict:
    value = " ".join(str(text or "").split()).strip(" .,!?:;-\n\t")
    for pattern in _VEHICLE_PATTERNS:
        match = pattern.search(value)
        if match:
            vehicle = match.group("value").strip(" .,!?:;-\n\t")
            if vehicle:
                return {"preferences": {"vehicle": vehicle[:120]}}
    return {}
