"""Small async Google Calendar OAuth/REST adapter.

Tokens are kept in the user's private JSON settings for now. They are never
returned by the API or written to logs; production deployments must protect
the database and backups accordingly.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import aiohttp

from config import config

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_URL = "https://www.googleapis.com/calendar/v3"
SCOPES = (
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
)


def configured() -> bool:
    return bool(config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET and config.GOOGLE_REDIRECT_URI)


def _secret() -> bytes:
    if not config.APP_AUTH_SECRET:
        raise RuntimeError("APP_AUTH_SECRET is not configured")
    return config.APP_AUTH_SECRET.get_secret_value().encode()


def make_state(user_id: int) -> str:
    payload = f"{user_id}:{int(time.time())}".encode()
    signature = hmac.new(_secret(), payload, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(payload + signature).decode().rstrip("=")


def read_state(state: str) -> int:
    try:
        raw = base64.urlsafe_b64decode(state + "=" * (-len(state) % 4))
        payload, signature = raw[:-16], raw[-16:]
        if not hmac.compare_digest(hmac.new(_secret(), payload, hashlib.sha256).digest()[:16], signature):
            raise ValueError
        user_id, created = payload.decode().split(":", 1)
        if time.time() - int(created) > 900:
            raise ValueError
        return int(user_id)
    except (ValueError, TypeError, UnicodeDecodeError):
        raise ValueError("invalid or expired Google OAuth state")


def authorization_url(user_id: int) -> str:
    if not configured():
        raise RuntimeError("Google Calendar is not configured")
    return AUTH_URL + "?" + urlencode({
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": make_state(user_id),
    })


async def exchange_code(code: str) -> dict:
    if not configured():
        raise RuntimeError("Google Calendar is not configured")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        async with session.post(TOKEN_URL, data={
            "code": code,
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET.get_secret_value(),
            "redirect_uri": config.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }) as response:
            data = await response.json()
            if response.status != 200 or not data.get("access_token"):
                raise RuntimeError("Google OAuth token exchange failed")
            return data


def token_data(user) -> dict:
    return dict((user.tech_stack or {}).get("google_calendar") or {})


def save_token(user, token: dict) -> None:
    settings = dict(user.tech_stack or {})
    previous = token_data(user)
    if not token.get("refresh_token") and previous.get("refresh_token"):
        token["refresh_token"] = previous["refresh_token"]
    settings["google_calendar"] = {
        key: token[key] for key in ("access_token", "refresh_token", "expires_in", "created_at", "scope", "token_type") if token.get(key) is not None
    }
    settings["google_calendar"]["created_at"] = int(time.time())
    user.tech_stack = settings


async def _access_token(user) -> str:
    token = token_data(user)
    if not token:
        raise RuntimeError("Google Calendar is not connected")
    created = int(token.get("created_at", 0))
    if token.get("access_token") and time.time() < created + int(token.get("expires_in", 3600)) - 60:
        return token["access_token"]
    refresh = token.get("refresh_token")
    if not refresh:
        raise RuntimeError("Google Calendar authorization expired; reconnect required")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        async with session.post(TOKEN_URL, data={
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET.get_secret_value(),
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        }) as response:
            data = await response.json()
            if response.status != 200 or not data.get("access_token"):
                raise RuntimeError("Google Calendar token refresh failed")
    save_token(user, data)
    return data["access_token"]


async def api_request(user, method: str, path: str, *, params: dict | None = None, body: dict | None = None):
    access_token = await _access_token(user)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        async with session.request(method, CALENDAR_URL + path, params=params, json=body, headers={"Authorization": f"Bearer {access_token}"}) as response:
            if response.status == 204:
                return {}
            data = await response.json()
            if response.status >= 400:
                raise RuntimeError(str(data.get("error", "Google Calendar request failed")))
            return data


async def list_calendars(user) -> list[dict]:
    data = await api_request(user, "GET", "/users/me/calendarList")
    return data.get("items", [])


async def list_events(user, calendar_id: str = "primary", time_min: str | None = None, time_max: str | None = None) -> list[dict]:
    params = {"singleEvents": "true", "orderBy": "startTime", "maxResults": "50"}
    if time_min: params["timeMin"] = time_min
    if time_max: params["timeMax"] = time_max
    return (await api_request(user, "GET", f"/calendars/{_calendar_id(calendar_id)}/events", params=params)).get("items", [])


async def create_event(user, event: dict, calendar_id: str = "primary") -> dict:
    return await api_request(user, "POST", f"/calendars/{_calendar_id(calendar_id)}/events", body=event)


async def delete_event(user, event_id: str, calendar_id: str = "primary") -> dict:
    return await api_request(user, "DELETE", f"/calendars/{_calendar_id(calendar_id)}/events/{event_id}")


def _calendar_id(value: str) -> str:
    from urllib.parse import quote
    return quote((value or "primary").strip(), safe="")
