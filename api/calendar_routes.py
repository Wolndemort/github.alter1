"""Google Calendar OAuth and user-scoped event routes."""
from __future__ import annotations

from aiohttp import web

from api.auth_routes import _bearer, _json
from data.database import async_session
from data.models import User
from services import google_calendar


def _provider_error(exc: Exception):
    if "not configured" in str(exc).lower():
        raise web.HTTPServiceUnavailable(text="Google Calendar is not configured")
    raise web.HTTPBadGateway(text="Google Calendar request failed")


async def calendar_connect_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    try:
        return web.json_response({"authorization_url": google_calendar.authorization_url(user_id)})
    except Exception as exc:
        _provider_error(exc)


async def calendar_callback_route(request: web.Request) -> web.Response:
    error = request.query.get("error")
    if error:
        return web.Response(text=f"Google Calendar authorization cancelled: {error}", content_type="text/plain", status=400)
    try:
        user_id = google_calendar.read_state(request.query.get("state", ""))
        token = await google_calendar.exchange_code(request.query.get("code", ""))
        async with async_session() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise web.HTTPNotFound(text="account not found")
            google_calendar.save_token(user, token)
            await session.commit()
        return web.Response(text="ALTER: Google Calendar подключён. Можно закрыть это окно.", content_type="text/plain")
    except web.HTTPException:
        raise
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    except Exception as exc:
        _provider_error(exc)


async def calendar_status_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None: raise web.HTTPUnauthorized(text="account not found")
        token = google_calendar.token_data(user)
        return web.json_response({"configured": google_calendar.configured(), "connected": bool(token.get("refresh_token") or token.get("access_token"))})


async def calendar_list_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None: raise web.HTTPUnauthorized(text="account not found")
        try: return web.json_response({"calendars": await google_calendar.list_calendars(user)})
        except Exception as exc: _provider_error(exc)


async def calendar_events_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None: raise web.HTTPUnauthorized(text="account not found")
        try:
            events = await google_calendar.list_events(user, request.query.get("calendar_id", "primary"), request.query.get("time_min"), request.query.get("time_max"))
            return web.json_response({"events": events})
        except Exception as exc: _provider_error(exc)


async def calendar_create_event_route(request: web.Request) -> web.Response:
    user_id = _bearer(request); payload = await _json(request)
    event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
    if not isinstance(event, dict) or not event.get("summary") or not isinstance(event.get("start"), dict) or not isinstance(event.get("end"), dict):
        raise web.HTTPBadRequest(text="summary, start and end are required")
    if len(str(event)) > 10000: raise web.HTTPBadRequest(text="event is too large")
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None: raise web.HTTPUnauthorized(text="account not found")
        try: return web.json_response(await google_calendar.create_event(user, event, payload.get("calendar_id", "primary")), status=201)
        except Exception as exc: _provider_error(exc)


async def calendar_delete_event_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None: raise web.HTTPUnauthorized(text="account not found")
        try:
            await google_calendar.delete_event(user, request.match_info["event_id"], request.query.get("calendar_id", "primary"))
            return web.json_response({"ok": True})
        except Exception as exc: _provider_error(exc)


def setup_calendar_routes(app: web.Application) -> None:
    app.router.add_get("/api/v1/calendar/connect", calendar_connect_route)
    app.router.add_get("/api/v1/calendar/oauth/callback", calendar_callback_route)
    app.router.add_get("/api/v1/calendar/status", calendar_status_route)
    app.router.add_get("/api/v1/calendar/calendars", calendar_list_route)
    app.router.add_get("/api/v1/calendar/events", calendar_events_route)
    app.router.add_post("/api/v1/calendar/events", calendar_create_event_route)
    app.router.add_delete("/api/v1/calendar/events/{event_id}", calendar_delete_event_route)
