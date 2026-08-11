"""Cheap deterministic quality gate for generated replies."""

from dataclasses import dataclass
import re


PUBLIC_FALLBACK = "Понял тебя. Сформулируй, пожалуйста, что именно нужно сделать — отвечу коротко и по делу."


@dataclass(frozen=True)
class ReplyQuality:
    score: int
    issues: tuple[str, ...]


def has_internal_leak(reply: str) -> bool:
    """Return True when a model reply looks like exposed planning notes."""
    return "internal_details" in assess_reply(reply).issues


def has_language_mismatch(reply: str, request: str) -> bool:
    """Detect an English answer to a clearly Russian request."""
    answer = re.findall(r"[A-Za-zА-Яа-яЁё]", reply or "")
    source = re.findall(r"[A-Za-zА-Яа-яЁё]", request or "")
    if not answer or not source:
        return False
    russian_chars = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
    russian_request = sum(char.lower() in russian_chars for char in source) / len(source)
    latin_answer = sum(char.isascii() and char.isalpha() for char in answer) / len(answer)
    return russian_request >= 0.35 and latin_answer >= 0.55


def sanitize_public_reply(reply: str) -> str:
    """Never expose prompts, roles, tool payloads, or planner notes to clients."""
    value = str(reply or "").strip()
    lowered = value.casefold()
    forbidden = (
        "<user_memory>", "</user_memory>", "system prompt", "developer message",
        "response policy", "tool_calls", "chain of thought", "internal reasoning",
    )
    return PUBLIC_FALLBACK if not value or any(marker in lowered for marker in forbidden) or has_internal_leak(value) else value


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
    leaked_markers = (
        "tool_calls", '"status":', "system prompt", "developer message", "chain of thought",
        "we need to answer", "we need to browse", "let's do a search", "let's simulate",
        "as ai,", "as an ai", "search terms:", "we should use", "need to check",
        "internal reasoning", "internal notes", "final answer:",
        "the user just mentioned", "the user mentioned", "looking at the memory",
        "memory section in the instructions", "according to the rules",
        "the tools available", "the system expects", "i need to store",
        "i should use the memory", "but wait, the tools", "which means they just",
        "internal response mode", "the memory shows", "character guidelines",
        "key constraints", "first, i need to", "looking back at the history",
        "check memory for", "per guidelines", "noting their tone", "my role as alter",
        "the user is feeling", "the user just shifted", "important: don't",
    )
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
