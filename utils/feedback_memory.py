"""Turn answer ratings into compact, reusable personal style guidance."""
from __future__ import annotations


def feedback_context(settings: dict | None, limit: int = 6) -> list[dict[str, str]]:
    values = (settings or {}).get("reply_feedback", [])
    if not isinstance(values, list):
        return []
    result = []
    for item in values[-limit:]:
        if not isinstance(item, dict) or item.get("rating") not in {"positive", "negative"}:
            continue
        answer = str(item.get("answer") or "").strip()
        if not answer:
            continue
        result.append({
            "rating": str(item["rating"]),
            "answer": answer[:700],
            **({"question": str(item.get("question") or "")[:300]} if item.get("question") else {}),
        })
    return result
