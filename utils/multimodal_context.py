"""Compact, evidence-only context records shared by every media pipeline."""
from __future__ import annotations

import json
from typing import Any


MAX_CONTEXT_CHARS = 7000


def _bounded(value: Any, limit: int = 6000) -> str:
    return str(value or "").strip()[:limit]


def attachment_context_message(
    *,
    kind: str,
    filename: str,
    media_type: str = "",
    transcript: str = "",
    observation: str = "",
    profile: dict | None = None,
    operation: str = "analysis",
    artifact_filename: str = "",
    artifact_media_type: str = "",
    artifact_id: str = "",
) -> str:
    """Build a bounded record safe to place in the conversation transcript.

    The record is evidence, not an instruction. Raw media is deliberately not
    persisted; the next model call receives only useful derived context and
    the name/type of any returned artifact.
    """
    payload = {
        "kind": _bounded(kind, 32),
        "filename": _bounded(filename, 180),
        "media_type": _bounded(media_type, 120),
        "operation": _bounded(operation, 64),
        "transcript": _bounded(transcript),
        "observation": _bounded(observation),
        "profile": profile if isinstance(profile, dict) else {},
        "artifact": {
            "id": _bounded(artifact_id, 80),
            "filename": _bounded(artifact_filename, 180),
            "media_type": _bounded(artifact_media_type, 120),
        },
    }
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return "<untrusted_attachment_context>\n" + content[:MAX_CONTEXT_CHARS] + "\n</untrusted_attachment_context>"
