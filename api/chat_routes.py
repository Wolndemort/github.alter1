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
from utils.quota import charge_user_id_credits, refund_user_id_credits
from services.media_jobs import cancel_job, get_job, history, submit_job
from services.elevenlabs_media import ElevenLabsError, design_voice, list_voices, speech_to_speech
from services.voice_commands import is_voice_change_request, is_voice_generation_request, requested_voice_id, voice_description
from utils.audio_actions import detect_audio_action, process_audio_action
from utils.capabilities import capabilities_reply, is_capabilities_request
from utils.reminders import is_reminder_request
from utils.request_routing import classify_request
from utils.metrics import increment
from utils.action_log import append_action
from utils.media_edit import DEFAULT_IMAGE_EDIT_PROMPT
from services.document_ingestion import edit_document, extract_document, start_document_agent
from services.vision_quality import compare_documents
from utils.agent_engine import agent_view


def _voice_generation_summary(generated: object) -> object:
    """Keep chat/SSE responses small; preview audio belongs to media APIs."""
    if not isinstance(generated, dict):
        return generated
    return {key: value for key, value in generated.items() if key not in {"previews", "audio_base64", "preview_url"}}


def _voice_preview_audio(generated: object) -> dict:
    if not isinstance(generated, dict) or not isinstance(generated.get("previews"), list):
        return {}
    preview = next((item for item in generated["previews"] if isinstance(item, dict)), None)
    if not preview:
        return {}
    audio = preview.get("audio_base_64") or preview.get("audio_base64")
    return {"audio_base64": audio, "audio_filename": "alter-voice-preview.mp3", "audio_mime": "audio/mpeg"} if audio else {}


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
        owner_access = has_owner_access(user_id, account.email if account else None)
        logging.info("chat access user_id=%s account_present=%s owner_access=%s", user_id, bool(account), owner_access)
        if not owner_access and not has_active_subscription(user):
            raise web.HTTPPaymentRequired(text="active subscription required")
        if not owner_access:
            redis = create_redis()
            try:
                if not await charge_user_id_credits(redis, user_id, 1, async_session):
                    raise web.HTTPTooManyRequests(text="monthly AI limit reached")
            finally:
                await close_redis(redis)
        message_text = str(payload.get("message") or "").strip()
        # Keep capability inventory deterministic across Telegram and mobile;
        # do not send this question through a generic model that may answer
        # with a vague "tell me what to do" prompt.
        if is_capabilities_request(message_text):
            return web.json_response({"reply": capabilities_reply(), "session_id": 0})
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
            return web.json_response({"reply": "Голос создан в ALTER. Вот его пробное звучание." if voice_id else "Голос сгенерирован. Вот пробное звучание; сервис не вернул идентификатор для сохранения.", "session_id": 0, "voice_id": voice_id or None, "voice_generation": _voice_generation_summary(generated), **_voice_preview_audio(generated)})
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


async def document_chat_route(request: web.Request) -> web.Response:
    """Extract a document and answer against its bounded text context."""
    user_id = _bearer(request)
    if not request.content_type.startswith("multipart/"):
        raise web.HTTPBadRequest(text="multipart form required")
    reader = await request.multipart()
    prompt = "Проанализируй документ и выдели главное."
    agent_mode = False
    agent_horizon = 60
    filename, content_type, data = "document", "", b""
    async for part in reader:
        if part.name == "prompt":
            prompt = (await part.text())[:2000] or prompt
        elif part.name == "agent":
            agent_mode = (await part.text()).strip().casefold() in {"1", "true", "yes", "on"}
        elif part.name == "horizon_minutes":
            try:
                agent_horizon = max(5, min(int((await part.text()).strip()), 60 * 24 * 90))
            except ValueError:
                raise web.HTTPBadRequest(text="horizon_minutes must be an integer")
        elif part.name == "file":
            filename = part.filename or filename
            content_type = part.headers.get("Content-Type", "")
            data = await part.read(decode=False)
    try:
        document = extract_document(filename, data, content_type)
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    async with async_session() as session:
        from data.models import User, WebAccount
        user = await session.get(User, user_id)
        account = (await session.execute(select(WebAccount).where(WebAccount.user_id == user_id))).scalar_one_or_none()
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        owner_access = has_owner_access(user_id, account.email if account else None)
        if not owner_access and not has_active_subscription(user):
            raise web.HTTPPaymentRequired(text="active subscription required")
        if not owner_access:
            redis = create_redis()
            try:
                if not await charge_user_id_credits(redis, user_id, 1, async_session):
                    raise web.HTTPTooManyRequests(text="monthly AI limit reached")
            finally:
                await close_redis(redis)
        agent = None
        if agent_mode:
            user.tech_stack = start_document_agent(user.tech_stack, document, prompt, horizon_minutes=agent_horizon)
            agent = agent_view(user.tech_stack)
        context = f"\n\nDOCUMENT: {document.filename}\n<document_text>\n{document.text}\n</document_text>"
        try:
            result = await ChatService().reply(session, user_id, prompt + context)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({"reply": result.reply, "session_id": result.session_id, "agent": agent, "document": {"filename": document.filename, "media_type": document.media_type, "chars": document.chars, "pages": document.pages}})


async def document_edit_route(request: web.Request) -> web.Response:
    """Apply explicit, auditable replacements and return the edited file."""
    user_id = _bearer(request)
    if not request.content_type.startswith("multipart/"):
        raise web.HTTPBadRequest(text="multipart form required")
    reader = await request.multipart()
    filename, content_type, data, instruction = "document", "", b"", ""
    async for part in reader:
        if part.name == "instruction":
            instruction = (await part.text())[:12000]
        elif part.name == "file":
            filename = part.filename or filename
            content_type = part.headers.get("Content-Type", "")
            data = await part.read(decode=False)
    try:
        artifact = edit_document(filename, data, instruction, content_type)
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    async with async_session() as session:
        from data.models import User, WebAccount
        user = await session.get(User, user_id)
        account = (await session.execute(select(WebAccount).where(WebAccount.user_id == user_id))).scalar_one_or_none()
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if not has_owner_access(user_id, account.email if account else None) and not has_active_subscription(user):
            raise web.HTTPPaymentRequired(text="active subscription required")
    response = web.Response(body=artifact.data, content_type=artifact.media_type or "application/octet-stream")
    response.headers["Content-Disposition"] = f'attachment; filename="{artifact.filename}"'
    response.headers["X-Alter-Edit-Mode"] = "explicit-replacements"
    return response


async def document_compare_route(request: web.Request) -> web.Response:
    """Compare two readable document versions without invoking an AI provider."""
    user_id = _bearer(request)
    if not request.content_type.startswith("multipart/"):
        raise web.HTTPBadRequest(text="multipart form required")
    reader = await request.multipart()
    versions = []
    async for part in reader:
        if part.name in {"before", "after"}:
            versions.append((part.name, part.filename or "document", part.headers.get("Content-Type", ""), await part.read(decode=False)))
    if {item[0] for item in versions} != {"before", "after"}:
        raise web.HTTPBadRequest(text="before and after files are required")
    extracted = {}
    try:
        for name, filename, media_type, data in versions:
            extracted[name] = extract_document(filename, data, media_type).text
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    async with async_session() as session:
        from data.models import User, WebAccount
        user = await session.get(User, user_id)
        account = (await session.execute(select(WebAccount).where(WebAccount.user_id == user_id))).scalar_one_or_none()
        if user is None:
            raise web.HTTPUnauthorized(text="account not found")
        if not has_owner_access(user_id, account.email if account else None) and not has_active_subscription(user):
            raise web.HTTPPaymentRequired(text="active subscription required")
    return web.json_response(compare_documents(extracted["before"], extracted["after"]))


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
        owner_access = has_owner_access(user_id, account.email if account else None)
        logging.info("stream access user_id=%s account_present=%s owner_access=%s", user_id, bool(account), owner_access)
        if not owner_access and not has_active_subscription(user):
            raise web.HTTPPaymentRequired(text="active subscription required")
        if not owner_access:
            redis = create_redis()
            try:
                if not await charge_user_id_credits(redis, user_id, 1, async_session):
                    raise web.HTTPTooManyRequests(text="monthly AI limit reached")
            finally:
                await close_redis(redis)
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
        await response.prepare(request)
        try:
            # Mobile uses the streaming endpoint for the composer. Handle
            # explicit Voice Design requests here as well; otherwise the
            # generic planner answers "I'm doing it" without calling
            # ElevenLabs at all.
            if is_voice_generation_request(text):
                description = voice_description(text)
                if not description:
                    raise web.HTTPBadRequest(text="voice description required")
                await response.write(("data: " + json.dumps({"type": "status", "status": "generating_voice"}, ensure_ascii=False) + "\n\n").encode("utf-8"))
                generated = await design_voice(description)
                voice_id = str(generated.get("voice_id") or generated.get("id") or "").strip()
                if voice_id:
                    settings = dict(user.tech_stack or {})
                    settings["generated_voice_id"] = voice_id
                    user.tech_stack = settings
                    await session.commit()
                reply = "Голос создан и сохранён." if voice_id else "Сервис создал голос, но не вернул его идентификатор."
                await response.write(("data: " + json.dumps({"type": "done", "reply": reply, "voice_id": voice_id or None, "voice_generation": _voice_generation_summary(generated)}, ensure_ascii=False) + "\n\n").encode("utf-8"))
                return response
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
        except ElevenLabsError as exc:
            logging.info("Voice generation was rejected user_id=%s reason=%s", user_id, str(exc)[:240])
            await response.write(("data: " + json.dumps({"type": "done", "reply": str(exc), "voice_id": None}, ensure_ascii=False) + "\n\n").encode("utf-8"))
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
        if kind not in {"image", "video"}:
            raise web.HTTPBadRequest(text="kind must be image or video")
        if kind == "image" and source is not None and not prompt:
            prompt = DEFAULT_IMAGE_EDIT_PROMPT
        redis = create_redis()
        try:
            if not await charge_user_id_credits(redis, user_id, cost, async_session):
                raise web.HTTPTooManyRequests(text="monthly media limit reached")
            append_action(user, "billing", "reserved", credits=cost, provider=config.MEDIA_PROVIDER, route="media")
            started_at = time.monotonic()
            artifact = await (generate_video(prompt, source, options) if kind == "video" else generate_image(prompt, source, options))
        except MediaGenerationError as exc:
            await refund_user_id_credits(redis, user_id, cost, async_session)
            append_action(user, "billing", "refunded", credits=cost, provider=config.MEDIA_PROVIDER, route="media")
            logging.warning("media generation failed user=%s kind=%s provider=%s elapsed_ms=%d error=%s", user_id, kind, config.MEDIA_PROVIDER, int((time.monotonic() - started_at) * 1000), str(exc)[:240])
            raise web.HTTPBadRequest(text=str(exc))
        finally:
            await close_redis(redis)
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
        job_id = await submit_job(user_id, kind, prompt, None, options)
    except Exception:
        await refund_user_id_credits(redis, user_id, cost, async_session)
        raise
    finally:
        await close_redis(redis)
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
    # Media payloads can be large (a finished video may be tens of MB). The
    # history screen needs metadata only; binary data is fetched from the
    # individual job-status endpoint when the user opens an item.
    items = [
        {key: value for key, value in item.items() if key != "data_base64"}
        for item in await history(user_id)
    ]
    return web.json_response({"items": items})


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
        settings = user.tech_stack or {}
        voice = settings.get("tts_voice")
        generated_voice_id = settings.get("generated_voice_id")
    # WAV is supported by AVFoundation on iOS; OGG/Opus is Telegram's format
    # but is not reliably playable by the native mobile audio stack.
    try:
        audio = await synthesize_speech(text, voice=voice, output_format="wav", fast=True, voice_id=generated_voice_id)
    except Exception:
        refund_redis = create_redis()
        try:
            await refund_user_id_credits(refund_redis, user_id, 5, async_session)
        finally:
            await close_redis(refund_redis)
        raise web.HTTPBadGateway(text="voice service temporarily unavailable")
    if not audio:
        raise web.HTTPServiceUnavailable(text="voice synthesis unavailable")
    return web.Response(body=audio, content_type="audio/wav")


def setup_chat_routes(app: web.Application) -> None:
    app.router.add_post("/api/v1/chat/messages", chat_route)
    app.router.add_post("/api/v1/chat/stream", chat_stream_route)
    app.router.add_post("/api/v1/chat/new", new_session_route)
    app.router.add_get("/api/v1/chat/history", history_route)
    app.router.add_post("/api/v1/chat/media", media_chat_route)
    app.router.add_post("/api/v1/chat/document", document_chat_route)
    app.router.add_post("/api/v1/chat/document/edit", document_edit_route)
    app.router.add_post("/api/v1/chat/document/compare", document_compare_route)
    app.router.add_post("/api/v1/media/generate", media_generate_route)
    app.router.add_get("/api/v1/media/capabilities", media_capabilities_route)
    app.router.add_post("/api/v1/media/jobs", media_job_create_route)
    app.router.add_get("/api/v1/media/jobs/{job_id}", media_job_status_route)
    app.router.add_post("/api/v1/media/jobs/{job_id}/cancel", media_job_cancel_route)
    app.router.add_get("/api/v1/media/history", media_history_route)
    app.router.add_post("/api/v1/voice/reply", voice_reply_route)
