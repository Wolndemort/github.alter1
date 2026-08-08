"""Authenticated ElevenLabs media routes."""
import base64

from aiohttp import web
from sqlalchemy import select

from api.auth_routes import _bearer, _json
from config import config
from data.database import async_session
from data.models import User, WebAccount
from services.elevenlabs_media import ElevenLabsError, isolate_audio, sound_effect
from utils.audio_actions import detect_audio_action, process_audio_action
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


async def process_audio_route(request: web.Request) -> web.Response:
    """Run a natural-language audio action on an optional uploaded recording.

    ``effect`` needs only ``prompt``; ``mix`` and ``isolate`` also require
    ``file``.  Keeping this adapter multipart makes it usable from both
    React Native and Telegram-side integrations without exposing provider
    details to either client.
    """
    user_id = _bearer(request)
    if not await _allowed(user_id):
        raise web.HTTPPaymentRequired(text="active subscription required")
    if not request.content_type.startswith("multipart/"):
        raise web.HTTPBadRequest(text="multipart form required")
    reader = await request.multipart()
    prompt, data, filename = "", b"", "audio.m4a"
    while True:
        field = await reader.next()
        if field is None:
            break
        if field.name == "prompt":
            prompt = (await field.text()).strip()
        elif field.name == "file":
            filename = field.filename or filename
            data = await field.read(decode=False)
    action = detect_audio_action(prompt)
    if action is None:
        raise web.HTTPBadRequest(text="prompt must describe an audio action")
    if action in {"mix", "isolate"} and not data:
        raise web.HTTPBadRequest(text="audio file required for this action")
    if len(data) > config.MEDIA_MAX_BYTES:
        raise web.HTTPBadRequest(text="invalid audio file")
    redis = create_redis()
    try:
        if not await charge_user_id_credits(redis, user_id, 20, async_session):
            raise web.HTTPTooManyRequests(text="monthly AI limit reached")
    finally:
        await close_redis(redis)
    try:
        result = await process_audio_action(prompt, data, filename)
    except (ElevenLabsError, RuntimeError) as exc:
        raise web.HTTPBadGateway(text=str(exc))
    if result is None:
        raise web.HTTPBadRequest(text="unsupported audio action")
    answer, audio = result
    return web.json_response({
        "reply": answer,
        "audio_base64": base64.b64encode(audio).decode("ascii"),
        "audio_filename": "alter-audio.mp3",
        "audio_mime": "audio/mpeg",
    })


def setup_elevenlabs_routes(app: web.Application) -> None:
    app.router.add_post("/api/v1/audio/sound-effects", sound_effect_route)
    app.router.add_post("/api/v1/audio/isolate", isolate_audio_route)
    app.router.add_post("/api/v1/audio/process", process_audio_route)
