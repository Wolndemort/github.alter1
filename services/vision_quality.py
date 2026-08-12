"""Deterministic quality utilities around the multimodal vision provider.

These helpers never invent visual facts: provider output is normalized,
compared and scored before it reaches an agent or an export route.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class VisionFinding:
    value: str
    confidence: float
    source: str = "vision"


def normalize_findings(items: list[dict] | None, *, source: str = "vision") -> list[VisionFinding]:
    result = []
    for item in items or []:
        value = str(item.get("value") or item.get("text") or "").strip()
        if not value:
            continue
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        result.append(VisionFinding(value, confidence, source))
    return result


def compare_documents(before: str, after: str) -> dict:
    """Return line-level additions/removals for contract/version review."""
    old, new = before.splitlines(), after.splitlines()
    removed = [line for line in old if line not in new]
    added = [line for line in new if line not in old]
    return {"changed": bool(removed or added), "added": added[:200], "removed": removed[:200], "change_count": len(added) + len(removed)}


def layout_edit_plan(text: str, replacements: list[dict]) -> dict:
    """Validate a non-destructive layout edit plan; actual rendering stays separate."""
    operations = []
    for item in replacements or []:
        old, new = str(item.get("old", "")), str(item.get("new", ""))
        if old and old in text:
            operations.append({"old": old, "new": new, "occurrences": text.count(old), "safe": True})
    return {"format": "layout-aware", "operations": operations, "requires_review": len(operations) != len(replacements or [])}


def object_geometry(x: float, y: float, width: float, height: float, image_width: int, image_height: int) -> dict:
    """Normalize a detected bounding box to 0..1 coordinates."""
    if image_width <= 0 or image_height <= 0:
        raise ValueError("image dimensions must be positive")
    values = [max(0.0, min(1.0, float(x) / image_width)), max(0.0, min(1.0, float(y) / image_height)), max(0.0, min(1.0, float(width) / image_width)), max(0.0, min(1.0, float(height) / image_height))]
    return dict(zip(("x", "y", "width", "height"), values))


def extract_chart_data(text: str) -> list[dict]:
    """Extract simple label/value pairs from OCR or chart descriptions."""
    values = []
    for label, number in re.findall(r"([\wА-Яа-я][\w А-Яа-я_-]{0,40})\s*[:|—-]\s*(-?\d+(?:[.,]\d+)?)", text or ""):
        values.append({"label": label.strip(), "value": float(number.replace(',', '.'))})
    return values[:200]


def video_events(transcript: str, *, max_events: int = 100) -> list[dict]:
    """Create timestamped candidate events from a transcript; vision verifies them."""
    events = []
    pattern = re.compile(r"(?:\[(\d{1,2}):(\d{2})\]|(\d{1,2}):(\d{2}))\s*(.+)")
    for match in pattern.finditer(transcript or ""):
        minutes, seconds = match.group(1) or match.group(3), match.group(2) or match.group(4)
        events.append({"at_seconds": int(minutes) * 60 + int(seconds), "description": match.group(5).strip(), "confidence": 0.5})
    return events[:max_events]


def quality_gate(findings: list[VisionFinding], *, minimum: float = 0.65) -> dict:
    accepted = [item for item in findings if item.confidence >= minimum]
    uncertain = [item.value for item in findings if item.confidence < minimum]
    return {"accepted": [item.value for item in accepted], "uncertain": uncertain, "requires_confirmation": bool(uncertain)}
