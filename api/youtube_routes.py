"""Protected YouTube search and audio adapter for the independent app."""
from __future__ import annotations

from urllib.parse import urlparse

from aiohttp import web

from api.auth_routes import _bearer, _json
from data.database import async_session
from data.models import User
from utils.audio_search import download_audio, remove_audio
from utils.billing import has_active_subscription, has_owner_access
from data.models import WebAccount
from sqlalchemy import select
from utils.youtube_search import search_youtube
from utils.redis_store import create_redis, close_redis, charge_credits
from config import config


async def _charge_youtube(user_id: int, cost: int) -> None:
    redis = create_redis()
    try:
        if not await charge_credits(redis, user_id, cost, config.MONTHLY_CREDITS):
            raise web.HTTPTooManyRequests(text="monthly YouTube limit reached")
    finally:
        await close_redis(redis)


def _youtube_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"youtube.com", "www.youtube.com", "youtu.be", "www.youtu.be"}:
        raise ValueError("youtube url required")
    return url


async def _require_access(request: web.Request):
    user_id = _bearer(request)
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None: raise web.HTTPUnauthorized(text="account not found")
        account = None
        if hasattr(session, "execute"):
            account = (await session.execute(select(WebAccount).where(WebAccount.user_id == user_id))).scalar_one_or_none()
        if not has_owner_access(user_id, account.email if account else None) and not has_active_subscription(user): raise web.HTTPPaymentRequired(text="active subscription required")
    return user_id


async def youtube_search_route(request: web.Request) -> web.Response:
    user_id = await _require_access(request)
    payload = await _json(request)
    query = str(payload.get("query", "")).strip()
    if not query or len(query) > 200: raise web.HTTPBadRequest(text="query is required")
    await _charge_youtube(user_id, config.YOUTUBE_SEARCH_CREDITS)
    return web.json_response({"results": await search_youtube(query, max_results=5)})


async def youtube_audio_route(request: web.Request) -> web.Response:
    user_id = await _require_access(request)
    payload = await _json(request)
    try: url = _youtube_url(payload.get("url"))
    except ValueError as exc: raise web.HTTPBadRequest(text=str(exc))
    await _charge_youtube(user_id, config.YOUTUBE_AUDIO_CREDITS)
    result = await download_audio(url)
    if result is None: raise web.HTTPBadGateway(text="audio download failed")
    path, title = result
    try:
        data = path.read_bytes()
        return web.Response(body=data, content_type="audio/mpeg", headers={"Content-Disposition": f'attachment; filename="ALTER.mp3"', "X-ALTER-Title": title[:120]})
    finally:
        remove_audio(path)


def setup_youtube_routes(app: web.Application) -> None:
    app.router.add_post("/api/v1/youtube/search", youtube_search_route)
    app.router.add_post("/api/v1/youtube/audio", youtube_audio_route)
