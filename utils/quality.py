"""Cheap deterministic quality gate for generated replies."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReplyQuality:
    score: int
    issues: tuple[str, ...]


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
    leaked_markers = ("tool_calls", '"status":', "system prompt", "developer message")
    if any(marker in lowered for marker in leaked_markers):
        issues.append("internal_details")
    if has_sources and "http" not in lowered and "источник" not in lowered and "источники" not in lowered:
        issues.append("missing_source_attribution")
    score = max(0, 100 - len(issues) * 25)
    return ReplyQuality(score=score, issues=tuple(issues))
