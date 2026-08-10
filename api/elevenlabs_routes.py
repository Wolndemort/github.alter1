"""Authenticated ElevenLabs media routes."""
import base64

from aiohttp import web
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from api.auth_routes import _bearer, _json
from config import config
from data.database import async_session
from data.models import User, WebAccount
from services.elevenlabs_media import ElevenLabsError, design_voice, isolate_audio, list_models, list_voices, sound_effect, speech_to_speech, speech_to_text
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
    except (ElevenLabsError, TypeError, ValueError) as exc:
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
    except (ElevenLabsError, TypeError, ValueError) as exc:
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


async def speech_to_text_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    if not await _allowed(user_id):
        raise web.HTTPPaymentRequired(text="active subscription required")
    if not request.content_type.startswith("multipart/"):
        raise web.HTTPBadRequest(text="multipart form required")
    reader = await request.multipart()
    field = await reader.next()
    if field is None or field.name != "file":
        raise web.HTTPBadRequest(text="audio file required")
    data = await field.read(decode=False)
    if not data or len(data) > config.MEDIA_MAX_BYTES:
        raise web.HTTPBadRequest(text="invalid audio file")
    try:
        return web.json_response(await speech_to_text(data, field.filename or "voice.m4a"))
    except ElevenLabsError as exc:
        raise web.HTTPBadGateway(text=str(exc))


async def speech_to_speech_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    if not await _allowed(user_id):
        raise web.HTTPPaymentRequired(text="active subscription required")
    voice_id = request.query.get("voice_id", "").strip()
    if not voice_id:
        raise web.HTTPBadRequest(text="voice_id query parameter required")
    if not request.content_type.startswith("multipart/"):
        raise web.HTTPBadRequest(text="multipart form required")
    reader = await request.multipart()
    field = await reader.next()
    if field is None or field.name != "file":
        raise web.HTTPBadRequest(text="audio file required")
    data = await field.read(decode=False)
    if not data or len(data) > config.MEDIA_MAX_BYTES:
        raise web.HTTPBadRequest(text="invalid audio file")
    try:
        return web.Response(body=await speech_to_speech(data, voice_id, field.filename or "voice.m4a"), content_type="audio/mpeg")
    except ElevenLabsError as exc:
        raise web.HTTPBadGateway(text=str(exc))


async def voices_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    if not await _allowed(user_id):
        raise web.HTTPPaymentRequired(text="active subscription required")
    try:
        return web.json_response(await list_voices())
    except ElevenLabsError as exc:
        raise web.HTTPBadGateway(text=str(exc))


async def models_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    if not await _allowed(user_id):
        raise web.HTTPPaymentRequired(text="active subscription required")
    try:
        return web.json_response({"models": await list_models()})
    except ElevenLabsError as exc:
        raise web.HTTPBadGateway(text=str(exc))


async def voice_generation_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    if not await _allowed(user_id):
        raise web.HTTPPaymentRequired(text="active subscription required")
    payload = await _json(request)
    try:
        generated = await design_voice(str(payload.get("description") or ""))
        voice_id = str(generated.get("voice_id") or generated.get("id") or "").strip() if isinstance(generated, dict) else ""
        if voice_id:
            async with async_session() as session:
                user = await session.get(User, user_id)
                if user is not None:
                    settings = dict(user.tech_stack or {})
                    settings["generated_voice_id"] = voice_id
                    user.tech_stack = settings
                    flag_modified(user, "tech_stack")
                    await session.commit()
        return web.json_response({**generated, "voice_id": voice_id or None} if isinstance(generated, dict) else generated)
    except (ElevenLabsError, TypeError, ValueError) as exc:
        raise web.HTTPBadGateway(text=str(exc))


def setup_elevenlabs_routes(app: web.Application) -> None:
    app.router.add_post("/api/v1/audio/sound-effects", sound_effect_route)
    app.router.add_post("/api/v1/audio/isolate", isolate_audio_route)
    app.router.add_post("/api/v1/audio/process", process_audio_route)
    app.router.add_post("/api/v1/audio/speech-to-text", speech_to_text_route)
    app.router.add_post("/api/v1/audio/speech-to-speech", speech_to_speech_route)
    app.router.add_get("/api/v1/audio/voices", voices_route)
    app.router.add_get("/api/v1/audio/models", models_route)
    app.router.add_post("/api/v1/audio/voice-generation", voice_generation_route)
