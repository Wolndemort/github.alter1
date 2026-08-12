"""Pure durable-agent state transitions.

The state is intentionally JSON-compatible so it can live in the existing
``User.tech_stack`` column while the execution layer remains transport- and
model-independent.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4


AGENT_KEY = "active_agent"
MAX_TASKS = 64


def _now(value: datetime | None = None) -> datetime:
    return value or datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _task(raw: object, index: int, *, start: datetime, horizon: int) -> dict:
    if isinstance(raw, str):
        raw = {"title": raw}
    if not isinstance(raw, dict):
        raw = {}
    title = str(raw.get("title") or raw.get("name") or f"Шаг {index + 1}").strip()[:240]
    task_id = str(raw.get("id") or f"task_{index + 1}_{uuid4().hex[:8]}").strip()[:64]
    dependencies = raw.get("depends_on") or raw.get("dependencies") or []
    if isinstance(dependencies, str):
        dependencies = [dependencies]
    if not isinstance(dependencies, list):
        dependencies = []
    try:
        priority = max(1, min(5, int(raw.get("priority", 3))))
    except (TypeError, ValueError):
        priority = 3
    due = _parse(raw.get("due_at"))
    if due is None:
        due = start + timedelta(minutes=max(1, int(horizon)) * (index + 1) / max(1, len(dependencies) + 1))
    return {
        "id": task_id,
        "title": title,
        "status": "pending",
        "priority": priority,
        "depends_on": [str(item)[:64] for item in dependencies[:16]],
        "due_at": _iso(due),
        "attempts": 0,
        "result": "",
        "blocked_reason": "",
    }


def _default_tasks(goal: str) -> list[dict]:
    return [
        {"id": "understand", "title": f"Уточнить результат по цели: {goal}"},
        {"id": "prepare", "title": "Собрать данные, ограничения и ресурсы", "depends_on": ["understand"]},
        {"id": "execute", "title": "Выполнить ближайший практический шаг", "depends_on": ["prepare"]},
        {"id": "verify", "title": "Проверить результат и определить следующий шаг", "depends_on": ["execute"]},
    ]


def start_agent(settings: dict | None, goal: str, *, horizon_minutes: int = 60,
                tasks: list[Any] | None = None, constraints: dict | None = None,
                now: datetime | None = None) -> dict:
    """Create or replace the active agent with a bounded task graph."""
    start = _now(now)
    horizon = max(5, min(int(horizon_minutes), 60 * 24 * 90))
    goal = str(goal or "").strip()[:1000]
    raw_tasks = tasks if tasks is not None else _default_tasks(goal)
    normalized = [_task(item, index, start=start, horizon=horizon) for index, item in enumerate(raw_tasks[:MAX_TASKS])]
    ids = {item["id"] for item in normalized}
    for item in normalized:
        item["depends_on"] = [dependency for dependency in item["depends_on"] if dependency in ids and dependency != item["id"]]
    result = dict(settings or {})
    result[AGENT_KEY] = {
        "id": uuid4().hex,
        "goal": goal,
        "horizon_minutes": horizon,
        "status": "active",
        "constraints": dict(constraints or {}),
        "tasks": normalized,
        "events": [{"type": "started", "at": _iso(start)}],
        "started_at": _iso(start),
        "updated_at": _iso(start),
    }
    return result


def _state(settings: dict | None) -> dict | None:
    value = (settings or {}).get(AGENT_KEY)
    return value if isinstance(value, dict) else None


def _touch(state: dict, now: datetime | None = None) -> None:
    state["updated_at"] = _iso(_now(now))


def next_ready_task(settings: dict | None) -> dict | None:
    state = _state(settings)
    if not state or state.get("status") not in {"active", "blocked"}:
        return None
    tasks = {item.get("id"): item for item in state.get("tasks", []) if isinstance(item, dict)}
    ready = [item for item in tasks.values() if item.get("status") == "pending" and all(tasks.get(dep, {}).get("status") == "done" for dep in item.get("depends_on", []))]
    ready.sort(key=lambda item: (int(item.get("priority", 3)), item.get("due_at", "")))
    return dict(ready[0]) if ready else None


def claim_next_task(settings: dict | None, *, now: datetime | None = None) -> dict:
    result = dict(settings or {})
    state = dict(_state(result) or {})
    if not state:
        return result
    task = next_ready_task(result)
    if task is None:
        if all(item.get("status") in {"done", "skipped"} for item in state.get("tasks", [])):
            state["status"] = "completed"
        result[AGENT_KEY] = state
        return result
    for item in state.get("tasks", []):
        if item.get("id") == task["id"]:
            item["status"] = "in_progress"
            item["attempts"] = int(item.get("attempts", 0)) + 1
            break
    state["status"] = "active"
    state.setdefault("events", []).append({"type": "task_claimed", "task_id": task["id"], "at": _iso(_now(now))})
    _touch(state, now)
    result[AGENT_KEY] = state
    return result


def complete_task(settings: dict | None, task_id: str, result_text: str = "", *, now: datetime | None = None) -> dict:
    return _finish_task(settings, task_id, "done", result_text, now=now)


def block_task(settings: dict | None, task_id: str, reason: str, *, now: datetime | None = None) -> dict:
    return _finish_task(settings, task_id, "blocked", reason, now=now)


def _finish_task(settings: dict | None, task_id: str, status: str, text: str, *, now: datetime | None = None) -> dict:
    result = dict(settings or {})
    state = dict(_state(result) or {})
    if not state:
        return result
    found = False
    for item in state.get("tasks", []):
        if item.get("id") == str(task_id):
            item["status"] = status
            if status == "done":
                item["result"] = str(text or "")[:2000]
                item["blocked_reason"] = ""
            else:
                item["blocked_reason"] = str(text or "Не указана причина")[:1000]
            found = True
            break
    if not found:
        return result
    state["status"] = "blocked" if status == "blocked" else "active"
    state.setdefault("events", []).append({"type": f"task_{status}", "task_id": str(task_id), "at": _iso(_now(now))})
    if all(item.get("status") in {"done", "skipped"} for item in state.get("tasks", [])):
        state["status"] = "completed"
    _touch(state, now)
    result[AGENT_KEY] = state
    return result


def replan_agent(settings: dict | None, tasks: list[Any], reason: str = "", *, now: datetime | None = None) -> dict:
    result = dict(settings or {})
    state = dict(_state(result) or {})
    if not state:
        return result
    existing_done = {item.get("id"): item for item in state.get("tasks", []) if item.get("status") in {"done", "skipped"}}
    rebuilt = start_agent({}, state.get("goal", ""), horizon_minutes=state.get("horizon_minutes", 60), tasks=tasks, constraints=state.get("constraints"), now=now)[AGENT_KEY]
    for item in rebuilt["tasks"]:
        previous = existing_done.get(item["id"])
        if previous:
            item.update({"status": previous.get("status"), "result": previous.get("result", "")})
    rebuilt["id"] = state.get("id", rebuilt["id"])
    rebuilt["events"] = list(state.get("events", [])) + [{"type": "replanned", "reason": str(reason)[:500], "at": _iso(_now(now))}]
    result[AGENT_KEY] = rebuilt
    return result


def agent_view(settings: dict | None) -> dict | None:
    state = _state(settings)
    if not state:
        return None
    result = dict(state)
    result["tasks"] = [dict(item) for item in state.get("tasks", [])]
    result["completed_tasks"] = sum(item.get("status") in {"done", "skipped"} for item in result["tasks"])
    result["total_tasks"] = len(result["tasks"])
    result["next_task"] = next_ready_task(settings)
    return result
