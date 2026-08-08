"""Cheap deterministic quality gate for generated replies."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ReplyQuality:
    score: int
    issues: tuple[str, ...]


def has_internal_leak(reply: str) -> bool:
    """Return True when a model reply looks like exposed planning notes."""
    return "internal_details" in assess_reply(reply).issues


def assess_reply(reply: str, *, has_sources: bool = False) -> ReplyQuality:
    text = (reply or "").strip()
    lowered = text.casefold()
    issues: list[str] = []
    if not text:
        issues.append("empty")
    if len(text) > 12000:
        issues.append("too_long")
    if text.count("?") > 1:
        issues.append("too_many_questions")
    leaked_markers = ("tool_calls", '"status":', "system prompt", "developer message", "chain of thought")
    reasoning_phrases = (
        "сначала проверю", "следует добавить", "нужно добавить", "ответ должен быть", "пользователь сказал", "пользователь написал",
        "я должен ответить", "нужно ответить пользователю", "следует ответить",
        "внутреннее рассуждение", "предыдущий диалог", "инструмент не нужен",
        "пользователь хочет", "пользователь просит", "сначала нужно понять",
    )
    # A single word such as «пользователь» is normal. Several planning phrases
    # together are a strong signal that the model exposed its working notes.
    planning_hits = sum(phrase in lowered for phrase in reasoning_phrases)
    if any(marker in lowered for marker in leaked_markers) or planning_hits >= 2 or re.search(r"(?:^|\n)\s*(?:анализ|рассуждение|план ответа)\s*:", lowered):
        issues.append("internal_details")
    if has_sources and "http" not in lowered and "источник" not in lowered and "источники" not in lowered:
        issues.append("missing_source_attribution")
    score = max(0, 100 - len(issues) * 25)
    return ReplyQuality(score=score, issues=tuple(issues))
