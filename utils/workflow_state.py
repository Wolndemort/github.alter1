"""Small persistent state machine for ALTER's outcome-oriented workflows."""

from datetime import datetime, timezone

WORKFLOW_KEY = "active_workflow"
DEFAULT_STEPS = ("Уточнить результат", "Сделать первый практический шаг", "Проверить результат")


def suggest_steps(goal: str, workflow_id: str = "finish_task") -> list[str]:
    value = str(goal or "").strip().casefold()
    if workflow_id == "decision":
        return ["Сформулировать варианты", "Сравнить критерии и риски", "Выбрать решение и первый шаг"]
    if workflow_id == "hard_conversation":
        return ["Определить цель разговора", "Подготовить ключевые фразы", "Провести разговор и разобрать итог"]
    if any(word in value for word in ("проект", "запуск", "продукт", "лендинг")):
        return ["Уточнить результат и ограничения", "Собрать план и ресурсы", "Сделать первый шаг", "Проверить результат"]
    return list(DEFAULT_STEPS)


def start_workflow(settings: dict | None, workflow_id: str, goal: str, steps=None) -> dict:
    value = dict(settings or {})
    normalized_steps = [str(item).strip()[:160] for item in (steps or suggest_steps(goal, workflow_id)) if str(item).strip()][:12]
    value[WORKFLOW_KEY] = {"id": str(workflow_id)[:48], "goal": str(goal).strip()[:500], "steps": normalized_steps or list(DEFAULT_STEPS), "current_step": 0, "status": "active", "started_at": datetime.now(timezone.utc).isoformat()}
    return value


def advance_workflow(settings: dict | None, complete: bool = False) -> dict:
    value = dict(settings or {})
    state = dict(value.get(WORKFLOW_KEY) or {})
    if not state:
        return value
    steps = list(state.get("steps") or DEFAULT_STEPS)
    current = min(int(state.get("current_step", 0)) + 1, len(steps) - 1)
    state["current_step"] = current
    state["status"] = "completed" if complete else ("ready_for_review" if current >= len(steps) - 1 else "active")
    value[WORKFLOW_KEY] = state
    return value


def workflow_view(settings: dict | None) -> dict | None:
    state = (settings or {}).get(WORKFLOW_KEY)
    if not isinstance(state, dict):
        return None
    result = dict(state)
    steps = list(result.get("steps") or DEFAULT_STEPS)
    index = min(max(int(result.get("current_step", 0)), 0), len(steps) - 1)
    result.update(current_step=index, current_step_title=steps[index], completed_steps=index, total_steps=len(steps))
    return result
