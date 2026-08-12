"""Tools exposed only to the durable agent executor."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from data.models import Reminder
from services.google_calendar import create_event, list_events
from utils.ap_logic import execute_tool
from utils.vector_memory import recall


AGENT_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Найди актуальную информацию в интернете и верни источники.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Получи текущую погоду для города.",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "map_geocode",
            "description": "Найди адрес или место через карты без изменения внешних данных.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agent_create_reminder",
            "description": "Создай напоминание только когда пользователь явно разрешил внешние действия.",
            "parameters": {"type": "object", "properties": {"text": {"type": "string"}, "remind_at": {"type": "string"}}, "required": ["text", "remind_at"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agent_list_reminders",
            "description": "Покажи будущие активные напоминания пользователя.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agent_recall_memory",
            "description": "Найди релевантный прошлый контекст пользователя.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agent_calendar_events",
            "description": "Прочитай события Google Calendar пользователя.",
            "parameters": {"type": "object", "properties": {"time_min": {"type": "string"}, "time_max": {"type": "string"}},},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agent_calendar_create",
            "description": "Создай событие Google Calendar только при разрешённых внешних действиях.",
            "parameters": {"type": "object", "properties": {"event": {"type": "object"}}, "required": ["event"]},
        },
    },
]


async def execute_agent_tool(name: str, arguments: dict, *, db, user, allow_external_actions: bool = False):
    if name in {"web_search", "get_weather", "map_geocode"}:
        return await execute_tool(name, arguments)
    if name == "agent_recall_memory":
        return await recall(db, user.id, str(arguments.get("query") or ""))
    if name in {"agent_create_reminder", "agent_calendar_create"} and not allow_external_actions:
        return {"status": "blocked", "reason": "Внешние действия не разрешены для этого агента."}
    if name == "agent_create_reminder":
        try:
            remind_at = datetime.fromisoformat(str(arguments.get("remind_at", "")).replace("Z", "+00:00"))
        except ValueError:
            return {"status": "blocked", "reason": "Неверный ISO datetime для напоминания."}
        if remind_at.tzinfo is None or remind_at <= datetime.now(timezone.utc):
            return {"status": "blocked", "reason": "Напоминание должно быть будущим и содержать timezone."}
        reminder = Reminder(user_id=user.id, text=str(arguments.get("text") or "")[:500], remind_at=remind_at)
        db.add(reminder)
        return {"status": "done", "result": f"Напоминание создано на {remind_at.isoformat()}"}
    if name == "agent_list_reminders":
        result = await db.execute(select(Reminder).where(Reminder.user_id == user.id, Reminder.is_sent.is_(False)).order_by(Reminder.remind_at).limit(20))
        return [{"text": item.text, "remind_at": item.remind_at.isoformat()} for item in result.scalars().all()]
    if name == "agent_calendar_events":
        return await list_events(user, time_min=arguments.get("time_min"), time_max=arguments.get("time_max"))
    if name == "agent_calendar_create":
        return await create_event(user, arguments.get("event") or {})
    return {"status": "blocked", "reason": f"Неизвестный agent tool: {name}"}
