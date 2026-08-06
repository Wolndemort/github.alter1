"""HTTP adapter for the shared chat use case."""

from aiohttp import web
from sqlalchemy import select
from config import config

from data.database import async_session
from services.chat_service import ChatService
from utils.billing import has_active_subscription, has_owner_access
from services.media_chat_service import reply as media_reply
from api.auth_routes import _bearer, _json


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
        try:
            result = await ChatService().reply(session, user_id, payload.get("message", ""))
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({"reply": result.reply, "session_id": result.session_id})


async def media_chat_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
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


def setup_chat_routes(app: web.Application) -> None:
    app.router.add_post("/api/v1/chat/messages", chat_route)
    app.router.add_post("/api/v1/chat/media", media_chat_route)
