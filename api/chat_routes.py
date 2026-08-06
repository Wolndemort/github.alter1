"""HTTP adapter for the shared chat use case."""

from aiohttp import web

from data.database import async_session
from services.chat_service import ChatService
from api.auth_routes import _bearer, _json


async def chat_route(request: web.Request) -> web.Response:
    user_id = _bearer(request)
    payload = await _json(request)
    async with async_session() as session:
        try:
            result = await ChatService().reply(session, user_id, payload.get("message", ""))
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({"reply": result.reply, "session_id": result.session_id})


def setup_chat_routes(app: web.Application) -> None:
    app.router.add_post("/api/v1/chat/messages", chat_route)
