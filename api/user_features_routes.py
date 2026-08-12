"""HTTP adapter for shared settings, reminders and check-ins."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiohttp import web
from sqlalchemy import select

from api.auth_routes import _bearer, _json
from data.database import async_session
from data.models import Reminder, User, WebAccount
from utils.action_log import read_actions
from utils.scenarios import get_scenario, list_scenarios
from utils.billing import has_owner_access
from utils.metrics import latency_snapshot, snapshot as metrics_snapshot
from utils.workflow_state import advance_workflow, start_workflow, workflow_view
from utils.agent_engine import agent_view, block_task, claim_next_task, complete_task, replan_agent, start_agent


def _parse_datetime(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("remind_at must be ISO datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError("remind_at timezone is required")
    return parsed


async def settings_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None: raise web.HTTPUnauthorized(text="account not found")
        return web.json_response({"settings": user.tech_stack or {}, "checkins_enabled": user.checkins_enabled})


async def update_settings_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    payload = await _json(request)
    allowed = {"voice_replies", "voice_auto_replies", "proactive_enabled", "private_mode", "tts_voice", "reply_feedback", "checkin_interval_hours", "health_followup_hours", "quiet_start", "quiet_end"}
    unknown = set(payload) - allowed
    if unknown: raise web.HTTPBadRequest(text="unknown setting")
    settings = dict(payload)
    ranges = {"checkin_interval_hours": (1, 168), "health_followup_hours": (1, 48), "quiet_start": (0, 23), "quiet_end": (0, 23)}
    for key, (low, high) in ranges.items():
        if key in settings:
            try: settings[key] = int(settings[key])
            except (TypeError, ValueError): raise web.HTTPBadRequest(text=f"invalid {key}")
            if not low <= settings[key] <= high: raise web.HTTPBadRequest(text=f"invalid {key}")
    if "voice_replies" in settings and not isinstance(settings["voice_replies"], bool):
        raise web.HTTPBadRequest(text="invalid voice_replies")
    if "voice_auto_replies" in settings and not isinstance(settings["voice_auto_replies"], bool):
        raise web.HTTPBadRequest(text="invalid voice_auto_replies")
    if "proactive_enabled" in settings and not isinstance(settings["proactive_enabled"], bool):
        raise web.HTTPBadRequest(text="invalid proactive_enabled")
    if "private_mode" in settings and not isinstance(settings["private_mode"], bool):
        raise web.HTTPBadRequest(text="invalid private_mode")
    if "tts_voice" in settings and settings["tts_voice"] not in {"alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse", "elevenlabs"}:
        raise web.HTTPBadRequest(text="invalid tts_voice")
    if "reply_feedback" in settings and (not isinstance(settings["reply_feedback"], list) or len(settings["reply_feedback"]) > 100):
        raise web.HTTPBadRequest(text="invalid reply_feedback")
    if "reply_feedback" in settings:
        for item in settings["reply_feedback"]:
            if not isinstance(item, dict) or item.get("rating") not in {"positive", "negative"}:
                raise web.HTTPBadRequest(text="invalid reply_feedback item")
            if len(str(item.get("answer") or "")) > 700 or len(str(item.get("question") or "")) > 300:
                raise web.HTTPBadRequest(text="reply_feedback item is too long")
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None: raise web.HTTPUnauthorized(text="account not found")
        merged = dict(user.tech_stack or {}); merged.update(settings); user.tech_stack = merged
        await session.commit()
        return web.json_response({"settings": merged, "checkins_enabled": user.checkins_enabled})


async def action_log_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        return web.json_response({"items": read_actions(user), "private_mode": bool((user.tech_stack or {}).get("private_mode"))})


async def scenarios_route(request: web.Request) -> web.Response:
    _bearer(request)
    return web.json_response({"items": list_scenarios()})


async def latency_diagnostics_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        user = await session.get(User, user_id)
        account = (await session.execute(select(WebAccount).where(WebAccount.user_id == user_id))).scalar_one_or_none()
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if not has_owner_access(user_id, account.email if account else None):
            raise web.HTTPForbidden(text="owner access required")
    return web.json_response({"latency": latency_snapshot()})


async def quality_diagnostics_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        user = await session.get(User, user_id)
        account = (await session.execute(select(WebAccount).where(WebAccount.user_id == user_id))).scalar_one_or_none()
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if not has_owner_access(user_id, account.email if account else None):
            raise web.HTTPForbidden(text="owner access required")
    counters = metrics_snapshot()
    return web.json_response({
        "counters": counters,
        "latency": latency_snapshot(),
        "tool_success": counters.get("ai.tool.ok", 0),
        "tool_empty": counters.get("ai.tool.empty", 0),
        "tool_failures": counters.get("ai.tool.failure", 0) + counters.get("ai.tool.error", 0),
        "quality_warnings": sum(value for name, value in counters.items() if name == "ai.reply.quality_warning"),
    })


async def workflow_start_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    payload = await _json(request)
    workflow_id = str(payload.get("workflow_id") or "finish_task").strip()
    goal = str(payload.get("goal") or "").strip()
    scenario = get_scenario(workflow_id)
    if scenario and not goal:
        goal = scenario["prompt"]
    if not goal:
        raise web.HTTPBadRequest(text="goal is required")
    steps = payload.get("steps")
    if steps is None and scenario:
        steps = scenario.get("workflow_steps") or None
    if steps is not None and (not isinstance(steps, list) or len(steps) > 12):
        raise web.HTTPBadRequest(text="steps must be a list")
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if (user.tech_stack or {}).get("private_mode") is True:
            raise web.HTTPConflict(text="workflow persistence is disabled in private mode")
        user.tech_stack = start_workflow(user.tech_stack, workflow_id, goal, steps)
        await session.commit()
        return web.json_response({"workflow": workflow_view(user.tech_stack)})


async def workflow_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        return web.json_response({"workflow": workflow_view(user.tech_stack)})


async def workflow_next_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    payload = await _json(request)
    complete = payload.get("complete", False)
    if not isinstance(complete, bool):
        raise web.HTTPBadRequest(text="complete must be boolean")
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if (user.tech_stack or {}).get("private_mode") is True:
            raise web.HTTPConflict(text="workflow persistence is disabled in private mode")
        user.tech_stack = advance_workflow(user.tech_stack, complete=complete)
        await session.commit()
        return web.json_response({"workflow": workflow_view(user.tech_stack)})


async def agent_start_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    payload = await _json(request)
    goal = str(payload.get("goal") or "").strip()
    if not goal:
        raise web.HTTPBadRequest(text="goal is required")
    try:
        horizon = int(payload.get("horizon_minutes", 60))
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="horizon_minutes must be an integer")
    tasks = payload.get("tasks")
    if tasks is not None and (not isinstance(tasks, list) or len(tasks) > 64):
        raise web.HTTPBadRequest(text="tasks must be a list with at most 64 items")
    constraints = payload.get("constraints") or {}
    if not isinstance(constraints, dict):
        raise web.HTTPBadRequest(text="constraints must be an object")
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if (user.tech_stack or {}).get("private_mode") is True:
            raise web.HTTPConflict(text="agent persistence is disabled in private mode")
        user.tech_stack = start_agent(user.tech_stack, goal, horizon_minutes=horizon, tasks=tasks, constraints=constraints)
        await session.commit()
        return web.json_response({"agent": agent_view(user.tech_stack)}, status=201)


async def agent_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        return web.json_response({"agent": agent_view(user.tech_stack)})


async def agent_next_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if (user.tech_stack or {}).get("private_mode") is True:
            raise web.HTTPConflict(text="agent persistence is disabled in private mode")
        user.tech_stack = claim_next_task(user.tech_stack)
        await session.commit()
        return web.json_response({"agent": agent_view(user.tech_stack)})


async def agent_task_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    payload = await _json(request)
    task_id = str(payload.get("task_id") or "").strip()
    status = str(payload.get("status") or "done").strip().casefold()
    if not task_id or status not in {"done", "blocked"}:
        raise web.HTTPBadRequest(text="task_id and status=done|blocked are required")
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if status == "done":
            user.tech_stack = complete_task(user.tech_stack, task_id, str(payload.get("result") or ""))
        else:
            user.tech_stack = block_task(user.tech_stack, task_id, str(payload.get("reason") or ""))
        await session.commit()
        return web.json_response({"agent": agent_view(user.tech_stack)})


async def agent_replan_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    payload = await _json(request)
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks or len(tasks) > 64:
        raise web.HTTPBadRequest(text="tasks must be a non-empty list with at most 64 items")
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        user.tech_stack = replan_agent(user.tech_stack, tasks, str(payload.get("reason") or ""))
        await session.commit()
        return web.json_response({"agent": agent_view(user.tech_stack)})


async def checkins_route(request: web.Request) -> web.Response:
    user_id = _bearer(request); payload = await _json(request)
    if not isinstance(payload.get("enabled"), bool): raise web.HTTPBadRequest(text="enabled must be boolean")
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None: raise web.HTTPUnauthorized(text="account not found")
        user.checkins_enabled = payload["enabled"]; await session.commit()
        return web.json_response({"checkins_enabled": user.checkins_enabled})


async def push_token_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    payload = await _json(request)
    push_token = str(payload.get("token", "")).strip()
    if not push_token.startswith(("ExponentPushToken[", "ExpoPushToken[")) or len(push_token) > 300:
        raise web.HTTPBadRequest(text="valid Expo push token required")
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        settings = dict(user.tech_stack or {})
        settings["expo_push_token"] = push_token
        user.tech_stack = settings
        await session.commit()
    return web.json_response({"ok": True})


async def reminders_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        result = await session.execute(select(Reminder).where(Reminder.user_id == user_id, Reminder.is_sent.is_(False)).order_by(Reminder.remind_at))
        return web.json_response({"reminders": [{"id": item.id, "text": item.text, "kind": item.kind, "remind_at": item.remind_at.isoformat()} for item in result.scalars().all()]})


async def create_reminder_route(request: web.Request) -> web.Response:
    user_id = _bearer(request); payload = await _json(request)
    text = str(payload.get("text", "")).strip()
    if not text: raise web.HTTPBadRequest(text="text is required")
    try: remind_at = _parse_datetime(payload.get("remind_at"))
    except ValueError as exc: raise web.HTTPBadRequest(text=str(exc))
    if remind_at <= datetime.now(timezone.utc): raise web.HTTPBadRequest(text="remind_at must be in the future")
    async with async_session() as session:
        reminder = Reminder(user_id=user_id, text=text[:500], remind_at=remind_at, follow_up_at=remind_at + timedelta(hours=2))
        session.add(reminder); await session.commit()
        return web.json_response({"id": reminder.id, "text": reminder.text, "remind_at": reminder.remind_at.isoformat()}, status=201)


async def delete_reminder_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    try: reminder_id = int(request.match_info["reminder_id"])
    except (KeyError, ValueError): raise web.HTTPBadRequest(text="invalid reminder id")
    async with async_session() as session:
        result = await session.execute(select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user_id, Reminder.is_sent.is_(False)))
        reminder = result.scalar_one_or_none()
        if reminder is None: raise web.HTTPNotFound(text="reminder not found")
        await session.delete(reminder); await session.commit()
    return web.json_response({"ok": True})


def setup_user_features_routes(app: web.Application) -> None:
    app.router.add_get("/api/v1/settings", settings_route)
    app.router.add_patch("/api/v1/settings", update_settings_route)
    app.router.add_get("/api/v1/action-log", action_log_route)
    app.router.add_get("/api/v1/scenarios", scenarios_route)
    app.router.add_get("/api/v1/diagnostics/latency", latency_diagnostics_route)
    app.router.add_get("/api/v1/diagnostics/quality", quality_diagnostics_route)
    app.router.add_post("/api/v1/workflow/start", workflow_start_route)
    app.router.add_get("/api/v1/workflow", workflow_route)
    app.router.add_post("/api/v1/workflow/next", workflow_next_route)
    app.router.add_post("/api/v1/agent/start", agent_start_route)
    app.router.add_get("/api/v1/agent", agent_route)
    app.router.add_post("/api/v1/agent/next", agent_next_route)
    app.router.add_post("/api/v1/agent/task", agent_task_route)
    app.router.add_post("/api/v1/agent/replan", agent_replan_route)
    app.router.add_post("/api/v1/checkins", checkins_route)
    app.router.add_post("/api/v1/push-token", push_token_route)
    app.router.add_get("/api/v1/reminders", reminders_route)
    app.router.add_post("/api/v1/reminders", create_reminder_route)
    app.router.add_delete("/api/v1/reminders/{reminder_id}", delete_reminder_route)
