"""Privacy-safe action history stored alongside user settings.

The log is deliberately metadata-only: no prompts, replies, tokens or memory
values are persisted here.
"""

from datetime import datetime, timezone

ACTION_LOG_KEY = "_action_log"
MAX_ACTIONS = 100


def append_action(user, action: str, status: str, **metadata) -> None:
    settings = dict(user.tech_stack or {})
    if settings.get("private_mode") is True:
        return
    allowed = {"route", "tool", "duration_ms", "count", "credits", "provider", "model"}
    entry = {
        "action": str(action)[:40],
        "status": str(status)[:24],
        "at": datetime.now(timezone.utc).isoformat(),
    }
    entry.update({key: str(value)[:80] for key, value in metadata.items() if key in allowed and value is not None})
    settings[ACTION_LOG_KEY] = [*(settings.get(ACTION_LOG_KEY) or [])[-(MAX_ACTIONS - 1):], entry]
    user.tech_stack = settings


def read_actions(user) -> list[dict]:
    value = (user.tech_stack or {}).get(ACTION_LOG_KEY, [])
    return [item for item in value if isinstance(item, dict)][-MAX_ACTIONS:]
