"""HTTP adapter for shared settings, reminders and check-ins."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiohttp import web
from sqlalchemy import select

from api.auth_routes import _bearer, _json
from data.database import async_session
from data.models import Reminder, User


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
    allowed = {"voice_replies", "voice_auto_replies", "tts_voice", "reply_feedback", "checkin_interval_hours", "health_followup_hours", "quiet_start", "quiet_end"}
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
    if "tts_voice" in settings and settings["tts_voice"] not in {"alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse", "elevenlabs"}:
        raise web.HTTPBadRequest(text="invalid tts_voice")
    if "reply_feedback" in settings and (not isinstance(settings["reply_feedback"], list) or len(settings["reply_feedback"]) > 100):
        raise web.HTTPBadRequest(text="invalid reply_feedback")
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None: raise web.HTTPUnauthorized(text="account not found")
        merged = dict(user.tech_stack or {}); merged.update(settings); user.tech_stack = merged
        await session.commit()
        return web.json_response({"settings": merged, "checkins_enabled": user.checkins_enabled})


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
    app.router.add_post("/api/v1/checkins", checkins_route)
    app.router.add_post("/api/v1/push-token", push_token_route)
    app.router.add_get("/api/v1/reminders", reminders_route)
    app.router.add_post("/api/v1/reminders", create_reminder_route)
    app.router.add_delete("/api/v1/reminders/{reminder_id}", delete_reminder_route)
