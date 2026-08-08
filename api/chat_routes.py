"""HTTP adapter for the shared chat use case."""

import base64

from aiohttp import web
from sqlalchemy import select
from config import config

from data.database import async_session
from services.chat_service import ChatService
from utils.billing import has_active_subscription, has_owner_access
from services.media_chat_service import reply as media_reply
from services.media_generation import MediaGenerationError, generate_image, generate_video
from api.auth_routes import _bearer, _json
from utils.tts import synthesize_speech
from utils.tasks import process_session
from utils.redis_store import create_redis, close_redis, charge_credits
from config import config


async def chat_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    payload = await _json(request)
    redis = create_redis()
    try:
        if not await charge_credits(redis, user_id, 1, config.MONTHLY_CREDITS):
            raise web.HTTPTooManyRequests(text="monthly AI limit reached")
    finally:
        await close_redis(redis)
    async with async_session() as session:
        from data.models import User, WebAccount
        user = await session.get(User, user_id)
        account = None
        if hasattr(session, "execute"):
            account = (await session.execute(select(WebAccount).where(WebAccount.user_id == user_id))).scalar_one_or_none()
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if not has_owner_access(user_id, account.email if account else None) and not has_active_subscription(user):
            raise web.HTTPPaymentRequired(text="active subscription required")
        try:
            location = payload.get("location")
            result = await ChatService().reply(session, user_id, payload.get("message", ""), location) if location else await ChatService().reply(session, user_id, payload.get("message", ""))
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({"reply": result.reply, "session_id": result.session_id})


async def new_session_route(request: web.Request) -> web.Response:
    """Close the active conversation, persist its summary, and start fresh."""
    user_id = _bearer(request)
    async with async_session() as session:
        from data.models import User, Session as ChatSession, WebAccount
        user = await session.get(User, user_id)
        account = (await session.execute(select(WebAccount).where(WebAccount.user_id == user_id))).scalar_one_or_none()
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if not has_owner_access(user_id, account.email if account else None) and not has_active_subscription(user):
            raise web.HTTPPaymentRequired(text="active subscription required")
        active = (await session.execute(select(ChatSession).where(
            ChatSession.user_id == user_id, ChatSession.is_processed.is_(False)
        ).order_by(ChatSession.started_at.desc()))).scalar_one_or_none()
        if active is not None and active.raw_messages:
            await process_session(active, session)
        else:
            await session.commit()
    return web.json_response({"ok": True})


async def history_route(request: web.Request) -> web.Response:
    """Return recent messages so mobile can restore the visible conversation."""
    user_id = _bearer(request)
    async with async_session() as session:
        from data.models import Session as ChatSession
        result = await session.execute(select(ChatSession).where(
            ChatSession.user_id == user_id,
            ChatSession.is_processed.is_(False),
        ).order_by(ChatSession.started_at.desc()))
        active = result.scalar_one_or_none()
        messages = list(active.raw_messages or []) if active else []
    return web.json_response({"session_id": active.id if active else None, "messages": messages[-100:]})


async def media_chat_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    redis = create_redis()
    try:
        if not await charge_credits(redis, user_id, 20, config.MONTHLY_CREDITS):
            raise web.HTTPTooManyRequests(text="monthly media limit reached")
    finally:
        await close_redis(redis)
    async with async_session() as session:
        from data.models import User, WebAccount
        user = await session.get(User, user_id)
        account = None
        if hasattr(session, "execute"):
            account = (await session.execute(select(WebAccount).where(WebAccount.user_id == user_id))).scalar_one_or_none()
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if not has_owner_access(user_id, account.email if account else None) and not has_active_subscription(user):
            raise web.HTTPPaymentRequired(text="active subscription required")
        if not request.content_type.startswith("multipart/"):
            raise web.HTTPBadRequest(text="multipart form required")
        reader = await request.multipart()
        prompt = ""
        content_type = ""
        data = b""
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "message":
                prompt = (await part.text()).strip()
            elif part.name == "file":
                content_type = part.headers.get("Content-Type", "application/octet-stream")
                chunks = []
                size = 0
                while True:
                    chunk = await part.read_chunk(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > config.MEDIA_MAX_BYTES:
                        raise web.HTTPRequestEntityTooLarge(max_size=config.MEDIA_MAX_BYTES, actual_size=size)
                    chunks.append(chunk)
                data = b"".join(chunks)
        try:
            result = await media_reply(session, user_id, prompt, content_type, data)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({"reply": result.reply, "session_id": result.session_id})


async def media_generate_route(request: web.Request) -> web.Response:
    """Generate/edit media through the same HTTP contract for mobile and bots."""
    user_id = _bearer(request)
    redis = create_redis()
    try:
        if not await charge_credits(redis, user_id, 40, config.MONTHLY_CREDITS):
            raise web.HTTPTooManyRequests(text="monthly media limit reached")
    finally:
        await close_redis(redis)
    async with async_session() as session:
        from data.models import User, WebAccount
        user = await session.get(User, user_id)
        account = (await session.execute(
            select(WebAccount).where(WebAccount.user_id == user_id)
        )).scalar_one_or_none()
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if not has_owner_access(user_id, account.email if account else None) and not has_active_subscription(user):
            raise web.HTTPPaymentRequired(text="active subscription required")
        if not request.content_type.startswith("multipart/"):
            raise web.HTTPBadRequest(text="multipart form required")
        reader = await request.multipart()
        prompt = ""
        kind = "image"
        source = None
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "message":
                prompt = (await part.text()).strip()
            elif part.name == "kind":
                kind = (await part.text()).strip().lower()
            elif part.name == "file":
                content_type = part.headers.get("Content-Type", "application/octet-stream")
                chunks, size = [], 0
                while True:
                    chunk = await part.read_chunk(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > config.MEDIA_MAX_BYTES:
                        raise web.HTTPRequestEntityTooLarge(max_size=config.MEDIA_MAX_BYTES, actual_size=size)
                    chunks.append(chunk)
                source = (content_type, b"".join(chunks))
        try:
            artifact = await (generate_video(prompt, source) if kind == "video" else generate_image(prompt, source))
        except MediaGenerationError as exc:
            raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({
        "media_type": artifact.media_type,
        "filename": artifact.filename,
        "data_base64": base64.b64encode(artifact.data).decode("ascii"),
    })


async def voice_reply_route(request: web.Request) -> web.Response:
    """Synthesize a short, explicitly requested mobile voice reply."""
    user_id = _bearer(request)
    redis = create_redis()
    try:
        if not await charge_credits(redis, user_id, 5, config.MONTHLY_CREDITS):
            raise web.HTTPTooManyRequests(text="monthly voice limit reached")
    finally:
        await close_redis(redis)
    payload = await _json(request)
    text = str(payload.get("text") or "").strip()
    if not text:
        raise web.HTTPBadRequest(text="text required")
    async with async_session() as session:
        from data.models import User, WebAccount
        user = await session.get(User, user_id)
        account = (await session.execute(select(WebAccount).where(WebAccount.user_id == user_id))).scalar_one_or_none()
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if not has_owner_access(user_id, account.email if account else None) and not has_active_subscription(user):
            raise web.HTTPPaymentRequired(text="active subscription required")
        voice = (user.tech_stack or {}).get("tts_voice")
    # WAV is supported by AVFoundation on iOS; OGG/Opus is Telegram's format
    # but is not reliably playable by the native mobile audio stack.
    audio = await synthesize_speech(text, voice=voice, output_format="wav")
    if not audio:
        raise web.HTTPServiceUnavailable(text="voice synthesis unavailable")
    return web.Response(body=audio, content_type="audio/wav")


def setup_chat_routes(app: web.Application) -> None:
    app.router.add_post("/api/v1/chat/messages", chat_route)
    app.router.add_post("/api/v1/chat/new", new_session_route)
    app.router.add_get("/api/v1/chat/history", history_route)
    app.router.add_post("/api/v1/chat/media", media_chat_route)
    app.router.add_post("/api/v1/media/generate", media_generate_route)
    app.router.add_post("/api/v1/voice/reply", voice_reply_route)
