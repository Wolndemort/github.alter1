"""Execution loop for the durable agent state."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from utils.agent_engine import agent_view, block_task, claim_next_task, complete_task, next_ready_task
from utils.ap_logic import chat_with_tools
from services.agent_tools import AGENT_TOOL_DEFINITIONS, execute_agent_tool


TaskExecutor = Callable[[dict, dict], Awaitable[str | dict[str, Any]]]


async def run_agent_step(settings: dict, executor: TaskExecutor) -> tuple[dict, dict | None]:
    """Claim and execute one ready task, converting failures into a blocked task."""
    task = next_ready_task(settings)
    if task is None:
        return settings, None
    claimed = claim_next_task(settings)
    try:
        result = await executor(task, agent_view(claimed) or {})
        if isinstance(result, dict) and str(result.get("status", "done")) == "blocked":
            updated = block_task(claimed, task["id"], str(result.get("reason") or "executor blocked the task"))
        else:
            text = result.get("result", "") if isinstance(result, dict) else result
            updated = complete_task(claimed, task["id"], str(text or ""))
    except Exception as exc:
        updated = block_task(claimed, task["id"], f"{type(exc).__name__}: {str(exc)[:400]}")
    return updated, task


async def run_agent_steps(settings: dict, executor: TaskExecutor, max_steps: int = 8) -> dict:
    """Run a bounded number of ready tasks; never spin on a blocked graph."""
    current = dict(settings or {})
    for _ in range(max(1, min(int(max_steps), 32))):
        current, task = await run_agent_step(current, executor)
        if task is None:
            break
        if (agent_view(current) or {}).get("status") in {"blocked", "completed"}:
            break
    return current


async def model_agent_executor(task: dict, state: dict, *, db=None, user=None) -> str | dict:
    """Execute a task with ALTER's existing model/tool loop."""
    prompt = (
        "Ты исполнитель задачи внутри долговременного плана ALTER. Выполни только текущую задачу, "
        "используй доступные инструменты, если они нужны, не выдумывай результат. Верни короткий "
        "итог и конкретный результат для следующего шага.\n\n"
        f"Цель: {state.get('goal', '')}\n"
        f"Текущая задача: {task.get('title', '')}\n"
        f"Ограничения: {state.get('constraints', {})}"
    )
    if db is None or user is None:
        response = await chat_with_tools([{"role": "user", "content": prompt}], task="planning")
    else:
        async def executor(name, arguments):
            return await execute_agent_tool(
                name, arguments, db=db, user=user,
                allow_external_actions=bool(state.get("constraints", {}).get("allow_external_actions")),
            )
        response = await chat_with_tools(
            [{"role": "user", "content": prompt}], task="planning",
            tool_definitions=AGENT_TOOL_DEFINITIONS, tool_executor=executor,
        )
    return str(getattr(response.choices[0].message, "content", "") or "").strip()
