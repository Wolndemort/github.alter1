"""HTTP adapter for application authentication.

This module knows about aiohttp only. Password/token rules live in
services.auth_service, so a future mobile client does not change the domain.
"""

from __future__ import annotations

from aiohttp import web

from config import config
from data.database import async_session
from services.auth_service import authenticate, issue_token, register


def _auth_secret() -> str:
    if config.APP_AUTH_SECRET is None:
        raise web.HTTPServiceUnavailable(text="Application authentication is not configured")
    return config.APP_AUTH_SECRET.get_secret_value()


async def _json(request: web.Request) -> dict:
    try:
        payload = await request.json()
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="JSON body required")
    if not isinstance(payload, dict):
        raise web.HTTPBadRequest(text="JSON object required")
    return payload


async def register_route(request: web.Request) -> web.Response:
    payload = await _json(request)
    try:
        async with async_session() as session:
            account = await register(session, str(payload.get("email", "")), str(payload.get("password", "")))
            await session.commit()
            token = issue_token(account.user_id, _auth_secret())
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({"access_token": token, "token_type": "bearer"}, status=201)


async def login_route(request: web.Request) -> web.Response:
    payload = await _json(request)
    try:
        async with async_session() as session:
            account = await authenticate(session, str(payload.get("email", "")), str(payload.get("password", "")))
            if account is None:
                raise web.HTTPUnauthorized(text="invalid credentials")
            token = issue_token(account.user_id, _auth_secret())
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({"access_token": token, "token_type": "bearer"})


def _bearer(request: web.Request) -> int:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise web.HTTPUnauthorized(text="bearer token required")
    from services.auth_service import verify_token

    try:
        return verify_token(header[7:].strip(), _auth_secret())
    except ValueError:
        raise web.HTTPUnauthorized(text="invalid or expired token")


async def me_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        from data.models import User

        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        return web.json_response({"id": user.id, "name": user.first_name, "subscription_expires_at": user.subscription_expires_at.isoformat() if user.subscription_expires_at else None})


def setup_auth_routes(app: web.Application) -> None:
    app.router.add_post("/api/v1/auth/register", register_route)
    app.router.add_post("/api/v1/auth/login", login_route)
    app.router.add_get("/api/v1/auth/me", me_route)
