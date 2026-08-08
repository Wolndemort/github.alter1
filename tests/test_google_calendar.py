import asyncio
from types import SimpleNamespace

import pytest
from aiohttp import web
from api import calendar_routes
from services import google_calendar


def run(coro):
    return asyncio.run(coro)


def setup_config(monkeypatch):
    monkeypatch.setattr(google_calendar.config, "APP_AUTH_SECRET", SimpleNamespace(get_secret_value=lambda: "auth-secret"))
    monkeypatch.setattr(google_calendar.config, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(google_calendar.config, "GOOGLE_CLIENT_SECRET", SimpleNamespace(get_secret_value=lambda: "client-secret"))
    monkeypatch.setattr(google_calendar.config, "GOOGLE_REDIRECT_URI", "https://api.alterai.ru/api/v1/calendar/oauth/callback")


def test_oauth_state_is_signed_and_round_trips(monkeypatch):
    setup_config(monkeypatch)
    state = google_calendar.make_state(42)
    assert google_calendar.read_state(state) == 42
    assert "client-id" in google_calendar.authorization_url(42)
    assert "calendar.events" in google_calendar.authorization_url(42)


def test_oauth_state_rejects_tampering(monkeypatch):
    setup_config(monkeypatch)
    state = google_calendar.make_state(42)
    altered = state[:-1] + ("A" if state[-1] != "A" else "B")
    try:
        google_calendar.read_state(altered)
    except ValueError:
        pass
    else:
        raise AssertionError("tampered state was accepted")


def test_save_token_preserves_refresh_token_on_refresh(monkeypatch):
    setup_config(monkeypatch)
    user = SimpleNamespace(tech_stack={"google_calendar": {"refresh_token": "refresh"}})
    google_calendar.save_token(user, {"access_token": "access", "expires_in": 3600})
    assert user.tech_stack["google_calendar"]["refresh_token"] == "refresh"
    assert "access_token" in user.tech_stack["google_calendar"]


def test_calendar_api_normalizes_event_list(monkeypatch):
    setup_config(monkeypatch)
    user = SimpleNamespace(tech_stack={"google_calendar": {"access_token": "access", "created_at": 9999999999, "expires_in": 3600}})

    async def fake_request(*args, **kwargs):
        return {"items": [{"id": "event-1", "summary": "Meeting"}]}

    monkeypatch.setattr(google_calendar, "api_request", fake_request)
    assert run(google_calendar.list_events(user))[0]["id"] == "event-1"


def test_calendar_routes_are_registered():
    app = web.Application()
    calendar_routes.setup_calendar_routes(app)
    paths = {resource.canonical for resource in app.router.resources()}
    assert "/api/v1/calendar/connect" in paths
    assert "/api/v1/calendar/oauth/callback" in paths
    assert "/api/v1/calendar/events" in paths


@pytest.mark.asyncio
async def test_calendar_create_validates_required_event_fields(monkeypatch):
    class Request:
        headers = {"Authorization": "Bearer token"}
        async def json(self): return {"summary": "missing times"}
    monkeypatch.setattr(calendar_routes, "_bearer", lambda request: 42)
    with pytest.raises(web.HTTPBadRequest):
        await calendar_routes.calendar_create_event_route(Request())
