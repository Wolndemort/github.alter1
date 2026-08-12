"""Backward-compatible structured memory updates with provenance metadata."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

META_KEY = "_meta"


def _now(value: datetime | None = None) -> datetime:
    return value or datetime.now(timezone.utc)


def _expires(category: str, key: str, value: str, now: datetime) -> str | None:
    # ALTER memory is permanent; facts change only when the user corrects or
    # explicitly deletes them.
    return None
    # Temporary states must not live forever; stable identity and preferences do.
    if key == "current_mood" or category == "important_events":
        return (now + timedelta(days=30)).isoformat()
    if category == "health_sport" and any(word in value.casefold() for word in ("болит", "температур", "кашел", "самочувств", "бессон")):
        return (now + timedelta(days=30)).isoformat()
    if category == "goals_habits" and key in {"goal", "focus"}:
        return (now + timedelta(days=180)).isoformat()
    return None


def merge_memory_facts(current: dict | None, incoming: dict | None, *, now: datetime | None = None) -> dict:
    """Merge facts without losing legacy values and record replacements."""
    stamp = _now(now)
    result = deepcopy(current) if isinstance(current, dict) else {}
    metadata = result.get(META_KEY) if isinstance(result.get(META_KEY), dict) else {}
    result[META_KEY] = metadata
    for category, fields in (incoming or {}).items():
        if category == META_KEY or not isinstance(fields, dict):
            continue
        target = result.setdefault(category, {})
        # Older memory records may contain a list at category level (notably
        # open_loops/important_events). Normalize that shape before merging so
        # one malformed legacy record can never break the whole chat handler.
        if isinstance(target, list):
            target = {"items": target}
            result[category] = target
        elif not isinstance(target, dict):
            target = {}
            result[category] = target
        category_meta = metadata.setdefault(category, {})
        for key, raw_value in fields.items():
            is_list = isinstance(raw_value, list)
            value = [str(item).strip() for item in raw_value if str(item).strip()] if is_list else (str(raw_value).strip() if raw_value is not None else "")
            if not value:
                continue
            old = target.get(key)
            entry = category_meta.setdefault(key, {"confidence": 0.85, "history": []})
            if old is not None and old != value:
                history = list(entry.get("history") or [])
                history.append({"value": str(old), "replaced_at": stamp.isoformat()})
                entry["history"] = history[-5:]
            if is_list and isinstance(old, list):
                value = list(dict.fromkeys([*old, *value]))[-20:]
            target[key] = value
            entry.update({"confidence": 0.9, "last_seen": stamp.isoformat()})
            entry.setdefault("first_seen", stamp.isoformat())
            expires = _expires(category, key, str(value), stamp)
            if expires:
                entry["expires_at"] = expires
            else:
                entry.pop("expires_at", None)
    return result


def purge_expired_memory(memory: dict | None, *, now: datetime | None = None) -> dict:
    # Compatibility shim: permanent memory is never silently purged.
    return deepcopy(memory) if isinstance(memory, dict) else {}
