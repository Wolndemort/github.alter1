"""HTTP adapter for application authentication.

This module knows about aiohttp only. Password/token rules live in
services.auth_service, so a future mobile client does not change the domain.
"""

from __future__ import annotations

from aiohttp import web
from aiogram import Bot
from sqlalchemy import select

from config import config
from data.database import async_session
from services.auth_service import authenticate, issue_token, register, resend_verification, verify_email
from services.account_linking import resolve_telegram_user
from utils.billing import create_payment, configured as billing_configured, has_active_subscription, has_owner_access, is_owner, price
from utils.redis_store import close_redis, create_link_token, create_redis, credits_used

_resolved_telegram_username: str | None = None


async def telegram_bot_username() -> str:
    """Resolve the username from BOT_TOKEN so stale env values cannot link to another bot."""
    global _resolved_telegram_username
    if _resolved_telegram_username:
        return _resolved_telegram_username
    fallback = (config.TELEGRAM_BOT_USERNAME or "").lstrip("@").strip()
    try:
        bot = Bot(token=config.BOT_TOKEN.get_secret_value())
        try:
            me = await bot.get_me()
        finally:
            await bot.session.close()
        _resolved_telegram_username = me.username or fallback
    except Exception:
        _resolved_telegram_username = fallback
    return _resolved_telegram_username


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
            "owner": has_owner_access(user.id, account.email),
            "payment_method_saved": bool(user.payment_method_id),
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


async def usage_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    redis = create_redis()
    try:
        used = await credits_used(redis, user_id)
    finally:
        await close_redis(redis)
    return web.json_response({"used": used, "limit": config.MONTHLY_CREDITS, "remaining": max(0, config.MONTHLY_CREDITS - used)})


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


async def auto_renew_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    payload = await _json(request)
    if not isinstance(payload.get("enabled"), bool):
        raise web.HTTPBadRequest(text="enabled must be boolean")
    async with async_session() as session:
        from data.models import User
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if payload["enabled"] and not user.payment_method_id:
            raise web.HTTPBadRequest(text="payment method is not saved")
        user.auto_renew = payload["enabled"]
        user.next_charge_at = user.subscription_expires_at if user.auto_renew else None
        await session.commit()
        return web.json_response({"auto_renew": user.auto_renew})


async def remove_payment_method_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        from data.models import User
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        user.payment_method_id = None
        user.auto_renew = False
        user.next_charge_at = None
        await session.commit()
    return web.json_response({"ok": True, "auto_renew": False, "payment_method_saved": False})


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
            url = await create_payment(session, user, await telegram_bot_username(), "bank_card")
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
    return web.json_response({"url": f"https://t.me/{await telegram_bot_username()}?start=link_{token}"})


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
    app.router.add_get("/api/v1/usage", usage_route)
    app.router.add_get("/api/v1/subscription", subscription_route)
    app.router.add_patch("/api/v1/subscription/auto-renew", auto_renew_route)
    app.router.add_delete("/api/v1/subscription/payment-method", remove_payment_method_route)
    app.router.add_post("/api/v1/subscription/create-payment", create_app_payment_route)
    app.router.add_post("/api/v1/telegram/link", start_telegram_link_route)
    app.router.add_post("/api/v1/auth/login", login_route)
    app.router.add_get("/api/v1/auth/me", me_route)
