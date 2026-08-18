"""Consent-safe response feedback and lightweight personal improvement loop."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from utils.quality import has_internal_leak

FEEDBACK_LIMIT = 100
POLL_INTERVAL = timedelta(hours=72)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_feedback(user, rating: str, *, question: str = "", answer: str = "", source: str = "unknown") -> dict:
    if rating not in {"positive", "negative"}:
        raise ValueError("rating must be positive or negative")
    answer = str(answer or "").strip()[:700]
    if not answer or has_internal_leak(answer):
        raise ValueError("answer is empty or unsafe")
    settings = dict(user.tech_stack or {})
    entries = [item for item in settings.get("reply_feedback", []) if isinstance(item, dict)]
    entry = {"rating": rating, "question": str(question or "")[:300], "answer": answer, "source": source[:32], "at": _now()}
    entries.append(entry)
    settings["reply_feedback"] = entries[-FEEDBACK_LIMIT:]
    settings["feedback_totals"] = {
        "positive": sum(1 for item in entries if item.get("rating") == "positive"),
        "negative": sum(1 for item in entries if item.get("rating") == "negative"),
    }
    user.tech_stack = settings
    return entry


def feedback_poll_due(user, now: datetime | None = None) -> bool:
    settings = dict(user.tech_stack or {})
    if settings.get("proactive_enabled", True) is False:
        return False
    raw = settings.get("last_feedback_poll_at")
    if not raw:
        return True
    try:
        last = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) - last >= POLL_INTERVAL


def mark_feedback_poll_sent(user, now: datetime | None = None) -> None:
    settings = dict(user.tech_stack or {})
    settings["last_feedback_poll_at"] = (now or datetime.now(timezone.utc)).isoformat()
    user.tech_stack = settings


def feedback_learning_context(user, limit: int = 6) -> list[dict[str, str]]:
    values = (user.tech_stack or {}).get("reply_feedback", [])
    result = []
    for item in values[-limit:] if isinstance(values, list) else []:
        if isinstance(item, dict) and item.get("rating") in {"positive", "negative"} and item.get("answer"):
            result.append({key: str(item[key])[:700 if key == "answer" else 300] for key in ("rating", "question", "answer") if item.get(key)})
    return result
