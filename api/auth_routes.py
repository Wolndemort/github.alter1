"""HTTP adapter for application authentication.

This module knows about aiohttp only. Password/token rules live in
services.auth_service, so a future mobile client does not change the domain.
"""

from __future__ import annotations

from aiohttp import web
from sqlalchemy import select

from config import config
from data.database import async_session
from services.auth_service import authenticate, issue_token, register, resend_verification, verify_email
from services.account_linking import resolve_telegram_user
from utils.billing import create_payment, configured as billing_configured, has_active_subscription, has_owner_access, is_owner, price
from utils.redis_store import close_redis, create_link_token, create_redis


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
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({"verification_required": True, "email": account.email}, status=202)


async def login_route(request: web.Request) -> web.Response:
    payload = await _json(request)
    try:
        async with async_session() as session:
            account = await authenticate(session, str(payload.get("email", "")), str(payload.get("password", "")))
            if account is None:
                raise web.HTTPUnauthorized(text="invalid credentials or email not verified")
            token = issue_token(account.user_id, _auth_secret())
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({"access_token": token, "token_type": "bearer"})


async def verify_email_route(request: web.Request) -> web.Response:
    payload = await _json(request)
    try:
        async with async_session() as session:
            account = await verify_email(session, str(payload.get("email", "")), str(payload.get("code", "")))
            await session.commit()
            token = issue_token(account.user_id, _auth_secret())
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({"access_token": token, "token_type": "bearer"})


async def resend_verification_route(request: web.Request) -> web.Response:
    payload = await _json(request)
    try:
        async with async_session() as session:
            await resend_verification(session, str(payload.get("email", "")))
            await session.commit()
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({"ok": True})


async def account_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        from data.models import User, WebAccount
        user = await session.get(User, user_id)
        account = (await session.execute(select(WebAccount).where(WebAccount.user_id == user_id))).scalar_one_or_none()
        if user is None or account is None:
            raise web.HTTPUnauthorized(text="account not found")
        return web.json_response({
            "id": user.id, "name": user.first_name, "email": account.email,
            "telegram_linked": account.telegram_user_id is not None,
            "subscription_expires_at": user.subscription_expires_at.isoformat() if user.subscription_expires_at else None,
            "auto_renew": user.auto_renew,
        })


async def memory_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        from data.models import User
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        return web.json_response({"memory": user.memory or {}, "tech_stack": user.tech_stack or {}})


async def subscription_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        from data.models import User, WebAccount
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        account = (await session.execute(select(WebAccount).where(WebAccount.user_id == user_id))).scalar_one_or_none()
        return web.json_response({
            "active": has_owner_access(user.id, account.email if account else None) or has_active_subscription(user),
            "price_rub": str(price()), "days": config.SUBSCRIPTION_DAYS,
            "expires_at": user.subscription_expires_at.isoformat() if user.subscription_expires_at else None,
            "auto_renew": user.auto_renew,
        })


async def create_app_payment_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    if not billing_configured():
        raise web.HTTPServiceUnavailable(text="payments are not configured")
    async with async_session() as session:
        from data.models import User
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        try:
            url = await create_payment(session, user, config.TELEGRAM_BOT_USERNAME, "bank_card")
        except RuntimeError as exc:
            raise web.HTTPBadGateway(text=str(exc))
        return web.json_response({"payment_url": url, "price_rub": str(price()), "days": config.SUBSCRIPTION_DAYS})


async def start_telegram_link_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    redis = create_redis()
    try:
        token = await create_link_token(redis, user_id)
    finally:
        await close_redis(redis)
    return web.json_response({"url": f"https://t.me/{config.TELEGRAM_BOT_USERNAME}?start=link_{token}"})


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
    app.router.add_post("/api/v1/auth/verify-email", verify_email_route)
    app.router.add_post("/api/v1/auth/resend-verification", resend_verification_route)
    app.router.add_get("/api/v1/account", account_route)
    app.router.add_get("/api/v1/memory", memory_route)
    app.router.add_get("/api/v1/subscription", subscription_route)
    app.router.add_post("/api/v1/subscription/create-payment", create_app_payment_route)
    app.router.add_post("/api/v1/telegram/link", start_telegram_link_route)
    app.router.add_post("/api/v1/auth/login", login_route)
    app.router.add_get("/api/v1/auth/me", me_route)
