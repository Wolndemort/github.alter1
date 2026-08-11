"""HTTP adapter for the shared chat use case."""

import base64
import asyncio
import json
import logging
import time

from aiohttp import web
from sqlalchemy import select
from config import config

from data.database import async_session
from services.chat_service import ChatService
from utils.billing import has_active_subscription, has_owner_access
from services.media_chat_service import reply as media_reply
from services.media_generation import MediaGenerationError, fal_capabilities, generate_image, generate_video
from api.auth_routes import _bearer, _json
from utils.tts import synthesize_speech
from utils.quality import sanitize_public_reply
from utils.tasks import process_session
from utils.redis_store import create_redis, close_redis
from utils.quota import charge_user_id_credits
from services.media_jobs import cancel_job, get_job, history, submit_job
from services.elevenlabs_media import ElevenLabsError, design_voice, list_voices, speech_to_speech
from services.voice_commands import is_voice_change_request, is_voice_generation_request, requested_voice_id, voice_description
from utils.audio_actions import detect_audio_action, process_audio_action
from utils.capabilities import is_capabilities_request
from utils.reminders import is_reminder_request
from utils.request_routing import classify_request
from utils.metrics import increment


async def chat_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    payload = await _json(request)
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
        if not has_owner_access(user_id, account.email if account else None):
            redis = create_redis()
            try:
                if not await charge_user_id_credits(redis, user_id, 1, async_session):
                    raise web.HTTPTooManyRequests(text="monthly AI limit reached")
            finally:
                await close_redis(redis)
        message_text = str(payload.get("message") or "").strip()
        if is_voice_generation_request(message_text):
            description = voice_description(message_text)
            if not description:
                raise web.HTTPBadRequest(text="опиши голос: например, спокойный низкий голос для подкаста")
            try:
                generated = await design_voice(description)
            except ElevenLabsError as exc:
                raise web.HTTPBadGateway(text=str(exc))
            voice_id = str(generated.get("voice_id") or generated.get("id") or "").strip()
            if voice_id:
                settings = dict(user.tech_stack or {})
                settings["generated_voice_id"] = voice_id
                user.tech_stack = settings
                await session.commit()
            return web.json_response({"reply": "Голос создан и сохранён. Теперь прикрепи голосовое и напиши: «измени мой голос на созданный»." if voice_id else "Сервис создал голос, но не вернул его идентификатор.", "session_id": 0, "voice_id": voice_id or None, "voice_generation": generated})
        if message_text.casefold().startswith(("покажи доступные голоса", "покажи голоса", "какие есть голоса")):
            try:
                voices = await list_voices()
            except ElevenLabsError as exc:
                raise web.HTTPBadGateway(text=str(exc))
            items = voices.get("voices", []) if isinstance(voices, dict) else []
            return web.json_response({"reply": "Доступные голоса: " + ", ".join(str(item.get("name") or item.get("voice_id")) for item in items[:30]), "voices": items})
        if detect_audio_action(payload.get("message", "")) == "effect":
            audio_redis = create_redis()
            try:
                if not await charge_user_id_credits(audio_redis, user_id, 20, async_session):
                    raise web.HTTPTooManyRequests(text="monthly audio limit reached")
            finally:
                await close_redis(audio_redis)
            audio_result = await process_audio_action(payload.get("message", ""), b"")
            if audio_result:
                answer, audio = audio_result
                return web.json_response({
                    "reply": answer,
                    "session_id": 0,
                    "audio_base64": base64.b64encode(audio).decode("ascii"),
                    "audio_filename": "alter-sound.mp3",
                    "audio_mime": "audio/mpeg",
                })
        try:
            location = payload.get("location")
            result = await ChatService().reply(session, user_id, payload.get("message", ""), location) if location else await ChatService().reply(session, user_id, payload.get("message", ""))
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc))
    payload = {"reply": result.reply, "session_id": result.session_id}
    if hasattr(result, "transcript"):
        payload["transcript"] = result.transcript
    return web.json_response(payload)


async def chat_stream_route(request: web.Request) -> web.StreamResponse:
    user_id = _bearer(request)
    payload = await _json(request)
    text = str(payload.get("message") or "").strip()
    route = classify_request(text)
    if not text or detect_audio_action(text) == "effect":
        raise web.HTTPConflict(text="stream unavailable for this request")
    async with async_session() as session:
        from data.models import User, WebAccount
        user = await session.get(User, user_id)
        account = (await session.execute(select(WebAccount).where(WebAccount.user_id == user_id))).scalar_one_or_none()
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if not has_owner_access(user_id, account.email if account else None) and not has_active_subscription(user):
            raise web.HTTPPaymentRequired(text="active subscription required")
        if not has_owner_access(user_id, account.email if account else None):
            redis = create_redis()
            try:
                if not await charge_user_id_credits(redis, user_id, 1, async_session):
                    raise web.HTTPTooManyRequests(text="monthly AI limit reached")
            finally:
                await close_redis(redis)
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
        await response.prepare(request)
        try:
            await response.write(("data: " + json.dumps({"type": "status", "status": route.initial_status}, ensure_ascii=False) + "\n\n").encode("utf-8"))
            if route.streamable:
                await response.write(("data: " + json.dumps({"type": "status", "status": "generating"}, ensure_ascii=False) + "\n\n").encode("utf-8"))
                async for delta in ChatService().stream_reply(session, user_id, text, payload.get("location")):
                    await response.write(("data: " + json.dumps({"type": "delta", "text": delta}, ensure_ascii=False) + "\n\n").encode("utf-8"))
            else:
                await response.write(("data: " + json.dumps({"type": "status", "status": "analyzing"}, ensure_ascii=False) + "\n\n").encode("utf-8"))
                async for delta in ChatService().stream_reply(session, user_id, text, payload.get("location"), use_tools=True):
                    await response.write(("data: " + json.dumps({"type": "delta", "text": delta}, ensure_ascii=False) + "\n\n").encode("utf-8"))
            await response.write(b"data: {\"type\":\"done\"}\n\n")
        except asyncio.CancelledError:
            increment("ai.reply.cancelled")
            logging.info("Streaming chat cancelled by client user_id=%s", user_id)
            raise
        except Exception:
            logging.exception("Streaming chat failed")
            await response.write(("data: " + json.dumps({"type": "error", "message": "stream failed"}) + "\n\n").encode("utf-8"))
        finally:
            await response.write_eof()
        return response


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
        ).order_by(ChatSession.started_at.desc()).limit(1))).scalar_one_or_none()
        if active is not None and active.raw_messages:
            await process_session(active, session)
        # Leave an empty active session as an explicit boundary. Otherwise the
        # next message would automatically inherit the previous conversation.
        session.add(ChatSession(user_id=user_id, raw_messages=[]))
        await session.commit()
    return web.json_response({"ok": True})


async def history_route(request: web.Request) -> web.Response:
    """Return recent messages so mobile can restore the visible conversation."""
    user_id = _bearer(request)
    async with async_session() as session:
        from data.models import Session as ChatSession
        result = await session.execute(select(ChatSession).where(
            ChatSession.user_id == user_id,
        ).order_by(ChatSession.started_at.desc()).limit(1))
        active = result.scalar_one_or_none()
        messages = [
            {"role": item.get("role"), "content": str(item.get("content") or "")}
            for item in (active.raw_messages or [])
            if isinstance(item, dict) and item.get("role") in {"user", "assistant"} and item.get("content")
        ] if active else []
    return web.json_response({"session_id": active.id if active else None, "messages": messages[-100:]})


async def media_chat_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    redis = create_redis()
    try:
        if not await charge_user_id_credits(redis, user_id, 20, async_session):
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
        filename = "audio.m4a"
        data = b""
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "message":
                prompt = (await part.text()).strip()
            elif part.name == "file":
                content_type = part.headers.get("Content-Type", "application/octet-stream")
                filename = part.filename or filename
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
            result = await media_reply(session, user_id, prompt, content_type, data, filename)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc))
    payload = {"reply": result.reply, "session_id": result.session_id, "transcript": result.transcript}
    if result.audio:
        payload.update({"audio_base64": base64.b64encode(result.audio).decode("ascii"), "audio_filename": result.audio_filename or "alter-audio.mp3", "audio_mime": "audio/mpeg"})
    if result.media_data:
        payload.update({"media_base64": base64.b64encode(result.media_data).decode("ascii"), "media_filename": result.media_filename or "alter-generated", "media_mime": result.media_type or "application/octet-stream"})
    return web.json_response(payload)


async def media_generate_route(request: web.Request) -> web.Response:
    """Generate/edit media through the same HTTP contract for mobile and bots."""
    user_id = _bearer(request)
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
        options = {}
        source = None
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "message":
                prompt = (await part.text()).strip()
            elif part.name == "kind":
                kind = (await part.text()).strip().lower()
            elif part.name == "options":
                try:
                    options = json.loads((await part.text()).strip() or "{}")
                except json.JSONDecodeError as exc:
                    raise web.HTTPBadRequest(text="options must be valid JSON") from exc
                if not isinstance(options, dict) or len(options) > 30:
                    raise web.HTTPBadRequest(text="options must be a JSON object")
                if set(options) & {"prompt", "image_url", "video_url"}:
                    raise web.HTTPBadRequest(text="prompt and source media are controlled by the request")
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
        cost = (
            config.FAL_TEXT_IMAGE_CREDITS if kind == "image" and source is None else
            config.FAL_TEXT_VIDEO_CREDITS if kind == "video" and source is None else
            config.MEDIA_GENERATION_CREDITS
        )
        redis = create_redis()
        try:
            if not await charge_user_id_credits(redis, user_id, cost, async_session):
                raise web.HTTPTooManyRequests(text="monthly media limit reached")
        finally:
            await close_redis(redis)
        started_at = time.monotonic()
        try:
            if kind not in {"image", "video"}:
                raise web.HTTPBadRequest(text="kind must be image or video")
            artifact = await (generate_video(prompt, source, options) if kind == "video" else generate_image(prompt, source, options))
        except MediaGenerationError as exc:
            logging.warning("media generation failed user=%s kind=%s provider=%s elapsed_ms=%d error=%s", user_id, kind, config.MEDIA_PROVIDER, int((time.monotonic() - started_at) * 1000), str(exc)[:240])
            raise web.HTTPBadRequest(text=str(exc))
        logging.info("media generation success user=%s kind=%s provider=%s model=%s bytes=%d elapsed_ms=%d cost=%d", user_id, kind, config.MEDIA_PROVIDER, (config.FAL_TEXT_VIDEO_MODEL if kind == "video" and source is None else config.FAL_VIDEO_MODEL if kind == "video" else config.FAL_TEXT_IMAGE_MODEL if source is None else config.FAL_IMAGE_MODEL), len(artifact.data), int((time.monotonic() - started_at) * 1000), cost)
    return web.json_response({
        "media_type": artifact.media_type,
        "filename": artifact.filename,
        "data_base64": base64.b64encode(artifact.data).decode("ascii"),
    })


async def media_capabilities_route(request: web.Request) -> web.Response:
    """Return configured media models/options; never returns API keys."""
    _bearer(request)
    return web.json_response(fal_capabilities())


async def media_job_create_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    payload = await _json(request)
    kind = str(payload.get("kind") or "").lower()
    prompt = str(payload.get("prompt") or "").strip()
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    if kind not in {"image", "video"} or not prompt:
        raise web.HTTPBadRequest(text="kind and prompt are required")
    cost = config.FAL_TEXT_VIDEO_CREDITS if kind == "video" else config.FAL_TEXT_IMAGE_CREDITS
    redis = create_redis()
    try:
        if not await charge_user_id_credits(redis, user_id, cost, async_session):
            raise web.HTTPTooManyRequests(text="monthly media limit reached")
    finally:
        await close_redis(redis)
    job_id = await submit_job(user_id, kind, prompt, None, options)
    return web.json_response({"job_id": job_id, "status": "queued", "progress": 0}, status=202)


async def media_job_status_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    job = await get_job(request.match_info["job_id"])
    if not job or job.get("user_id") != user_id:
        raise web.HTTPNotFound(text="job not found")
    return web.json_response(job)


async def media_job_cancel_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    if not await cancel_job(request.match_info["job_id"], user_id):
        raise web.HTTPNotFound(text="job not found")
    return web.json_response({"ok": True, "status": "cancelled"})


async def media_history_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    return web.json_response({"items": await history(user_id)})


async def voice_reply_route(request: web.Request) -> web.Response:
    """Synthesize a short, explicitly requested mobile voice reply."""
    user_id = _bearer(request)
    redis = create_redis()
    try:
        if not await charge_user_id_credits(redis, user_id, 5, async_session):
            raise web.HTTPTooManyRequests(text="monthly voice limit reached")
    finally:
        await close_redis(redis)
    payload = await _json(request)
    text = sanitize_public_reply(payload.get("text"))
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
    app.router.add_post("/api/v1/chat/stream", chat_stream_route)
    app.router.add_post("/api/v1/chat/new", new_session_route)
    app.router.add_get("/api/v1/chat/history", history_route)
    app.router.add_post("/api/v1/chat/media", media_chat_route)
    app.router.add_post("/api/v1/media/generate", media_generate_route)
    app.router.add_get("/api/v1/media/capabilities", media_capabilities_route)
    app.router.add_post("/api/v1/media/jobs", media_job_create_route)
    app.router.add_get("/api/v1/media/jobs/{job_id}", media_job_status_route)
    app.router.add_post("/api/v1/media/jobs/{job_id}/cancel", media_job_cancel_route)
    app.router.add_get("/api/v1/media/history", media_history_route)
    app.router.add_post("/api/v1/voice/reply", voice_reply_route)
