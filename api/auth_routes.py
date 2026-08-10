"""HTTP adapter for application authentication.

This module knows about aiohttp only. Password/token rules live in
services.auth_service, so a future mobile client does not change the domain.
"""

from __future__ import annotations

from aiohttp import web
from aiogram import Bot
from sqlalchemy import delete, select
from sqlalchemy.orm.attributes import flag_modified

from config import config
from data.database import async_session
from services.auth_service import authenticate, issue_token, register, resend_verification, verify_email
from datetime import datetime, timezone
from services.account_linking import resolve_telegram_user
from utils.billing import create_payment, configured as billing_configured, has_active_subscription, has_owner_access, is_owner, price, PLANS, normalize_plan, plan_info, credits_limit
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
            if not isinstance(payload.get("legal_accepted", False), bool):
                raise web.HTTPBadRequest(text="legal_accepted must be boolean")
            if payload.get("legal_accepted", False):
                account = await register(session, str(payload.get("email", "")), str(payload.get("password", "")), True)
            else:
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
            "subscription_plan": (user.tech_stack or {}).get("subscription_plan", "personal"),
            "legal_accepted": user.legal_accepted_at is not None,
        })


async def memory_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        from data.models import ImportantEvent, MemoryChunk, Session as ChatSession, User
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        from utils.memory_view import memory_sections
        event_result = await session.execute(select(ImportantEvent).where(ImportantEvent.user_id == user_id).order_by(ImportantEvent.occurred_at.desc()).limit(20))
        chunk_result = await session.execute(select(MemoryChunk).where(MemoryChunk.user_id == user_id).order_by(MemoryChunk.created_at.desc()).limit(20))
        active_result = await session.execute(select(ChatSession).where(ChatSession.user_id == user_id, ChatSession.is_processed.is_(False)).order_by(ChatSession.started_at.desc()))
        events = event_result.scalars().all() if hasattr(event_result, "scalars") else []
        chunks = chunk_result.scalars().all() if hasattr(chunk_result, "scalars") else []
        active = active_result.scalar_one_or_none() if hasattr(active_result, "scalar_one_or_none") else None
        extras = []
        if events:
            extras.append({"category": "important_events", "title": "Важные события", "items": [{"label": event.event_type, "value": event.title + (f": {event.description}" if event.description else "")} for event in events]})
        if chunks:
            extras.append({"category": "episodic_context", "title": "Контекст прошлых разговоров", "items": [{"label": chunk.source, "value": chunk.content} for chunk in chunks]})
        active_messages = getattr(active, "raw_messages", None) if active else None
        if active_messages:
            extras.append({"category": "current_context", "title": "Текущий разговор", "items": [{"label": item.get("role", ""), "value": item.get("content", "")} for item in active_messages[-10:] if item.get("content")]})
        return web.json_response({"sections": memory_sections(user.memory, extras)})


async def forget_memory_category_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    category = str(request.match_info.get("category") or "").strip()
    if not category or len(category) > 64 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in category):
        raise web.HTTPBadRequest(text="invalid memory category")
    async with async_session() as session:
        from data.models import ImportantEvent, MemoryChunk, Session as ChatSession, User
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if category == "episodic_context":
            deleted = await session.execute(delete(MemoryChunk).where(MemoryChunk.user_id == user_id))
            await session.commit()
            return web.json_response({"ok": True, "deleted": bool(deleted.rowcount) if hasattr(deleted, "rowcount") else True, "category": category})
        if category == "important_events":
            deleted = await session.execute(delete(ImportantEvent).where(ImportantEvent.user_id == user_id))
            await session.commit()
            return web.json_response({"ok": True, "deleted": bool(deleted.rowcount) if hasattr(deleted, "rowcount") else True, "category": category})
        if category == "current_context":
            active = (await session.execute(select(ChatSession).where(ChatSession.user_id == user_id, ChatSession.is_processed.is_(False)).order_by(ChatSession.started_at.desc()))).scalar_one_or_none()
            if active:
                active.raw_messages = []
                await session.commit()
            return web.json_response({"ok": True, "deleted": bool(active), "category": category})
        memory = dict(user.memory or {})
        existed = category in memory
        memory.pop(category, None)
        user.memory = memory
        flag_modified(user, "memory")
        await session.commit()
        return web.json_response({"ok": True, "deleted": existed, "category": category})


async def clear_memory_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        from data.models import ImportantEvent, MemoryChunk, User
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        user.memory = {}
        await session.execute(delete(ImportantEvent).where(ImportantEvent.user_id == user_id))
        await session.execute(delete(MemoryChunk).where(MemoryChunk.user_id == user_id))
        flag_modified(user, "memory")
        await session.commit()
        return web.json_response({"ok": True})


async def clear_context_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        from data.models import MemoryChunk, User
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        await session.execute(delete(MemoryChunk).where(MemoryChunk.user_id == user_id))
        await session.commit()
    return web.json_response({"ok": True})


async def usage_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        from data.models import User
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
    redis = create_redis()
    try:
        used = await credits_used(redis, user_id)
    finally:
        await close_redis(redis)
    limit = credits_limit(user)
    return web.json_response({"used": used, "limit": limit, "remaining": max(0, limit - used)})


async def subscription_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        from data.models import User, WebAccount
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        account = (await session.execute(select(WebAccount).where(WebAccount.user_id == user_id))).scalar_one_or_none()
        current_plan = normalize_plan((user.tech_stack or {}).get("subscription_plan"))
        return web.json_response({
            "active": has_owner_access(user.id, account.email if account else None) or has_active_subscription(user),
            "price_rub": str(price()), "days": config.SUBSCRIPTION_DAYS,
            "expires_at": user.subscription_expires_at.isoformat() if user.subscription_expires_at else None,
            "auto_renew": user.auto_renew,
            "plan": current_plan,
            "plans": [{"id": key, **value} for key, value in PLANS.items()],
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
    payload = await _json(request)
    plan = normalize_plan(payload.get("plan"))
    async with async_session() as session:
        from data.models import User
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        try:
            url = await create_payment(session, user, await telegram_bot_username(), "bank_card", plan)
        except RuntimeError as exc:
            raise web.HTTPBadGateway(text=str(exc))
        return web.json_response({"payment_url": url, "price_rub": str(price(plan)), "plan": plan, "days": config.SUBSCRIPTION_DAYS})


async def start_telegram_link_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    redis = create_redis()
    try:
        token = await create_link_token(redis, user_id)
    finally:
        await close_redis(redis)
    return web.json_response({"url": f"https://t.me/{await telegram_bot_username()}?start=link_{token}"})


async def accept_legal_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    async with async_session() as session:
        from data.models import User
        user = await session.get(User, user_id)
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        user.legal_accepted_at = user.legal_accepted_at or datetime.now(timezone.utc)
        await session.commit()
    return web.json_response({"ok": True, "legal_accepted": True})


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
    app.router.add_delete("/api/v1/memory/{category}", forget_memory_category_route)
    app.router.add_delete("/api/v1/memory", clear_memory_route)
    app.router.add_delete("/api/v1/context", clear_context_route)
    app.router.add_get("/api/v1/usage", usage_route)
    app.router.add_get("/api/v1/subscription", subscription_route)
    app.router.add_patch("/api/v1/subscription/auto-renew", auto_renew_route)
    app.router.add_delete("/api/v1/subscription/payment-method", remove_payment_method_route)
    app.router.add_post("/api/v1/subscription/create-payment", create_app_payment_route)
    app.router.add_post("/api/v1/telegram/link", start_telegram_link_route)
    app.router.add_post("/api/v1/legal/accept", accept_legal_route)
    app.router.add_post("/api/v1/auth/login", login_route)
    app.router.add_get("/api/v1/auth/me", me_route)
