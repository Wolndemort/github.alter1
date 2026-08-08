"""Authenticated ElevenLabs media routes."""
from aiohttp import web
from sqlalchemy import select

from api.auth_routes import _bearer, _json
from config import config
from data.database import async_session
from data.models import User, WebAccount
from services.elevenlabs_media import ElevenLabsError, isolate_audio, sound_effect
from utils.billing import has_active_subscription, has_owner_access
from utils.quota import charge_user_id_credits
from utils.redis_store import close_redis, create_redis


async def _allowed(user_id: int) -> bool:
    async with async_session() as session:
        user = await session.get(User, user_id)
        account = (await session.execute(select(WebAccount).where(WebAccount.user_id == user_id))).scalar_one_or_none()
        return bool(user and (has_owner_access(user_id, account.email if account else None) or has_active_subscription(user)))


async def sound_effect_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    if not await _allowed(user_id):
        raise web.HTTPPaymentRequired(text="active subscription required")
    payload = await _json(request)
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise web.HTTPBadRequest(text="prompt required")
    redis = create_redis()
    try:
        if not await charge_user_id_credits(redis, user_id, 20, async_session):
            raise web.HTTPTooManyRequests(text="monthly AI limit reached")
    finally:
        await close_redis(redis)
    try:
        return web.Response(body=await sound_effect(prompt), content_type="audio/mpeg")
    except ElevenLabsError as exc:
        raise web.HTTPBadGateway(text=str(exc))


async def isolate_audio_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    if not await _allowed(user_id):
        raise web.HTTPPaymentRequired(text="active subscription required")
    reader = await request.multipart()
    field = await reader.next()
    if field is None or field.name != "file":
        raise web.HTTPBadRequest(text="audio file required")
    data = await field.read(decode=False)
    if not data or len(data) > config.MEDIA_MAX_BYTES:
        raise web.HTTPBadRequest(text="invalid audio file")
    redis = create_redis()
    try:
        if not await charge_user_id_credits(redis, user_id, 20, async_session):
            raise web.HTTPTooManyRequests(text="monthly AI limit reached")
    finally:
        await close_redis(redis)
    try:
        return web.Response(body=await isolate_audio(data, field.filename or "audio"), content_type="audio/mpeg")
    except ElevenLabsError as exc:
        raise web.HTTPBadGateway(text=str(exc))


def setup_elevenlabs_routes(app: web.Application) -> None:
    app.router.add_post("/api/v1/audio/sound-effects", sound_effect_route)
    app.router.add_post("/api/v1/audio/isolate", isolate_audio_route)
